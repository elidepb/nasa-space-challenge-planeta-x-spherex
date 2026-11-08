"""Background preview rendering for one spectral group (S8).

The service consumes the ``Observation`` objects already built by Elide during
Phase 1 (each one carries its ``.image`` NumPy matrix in memory) and writes a
contrast-stretched PNG preview per frame into the images volume.

Everything that is CPU bound (NumPy statistics and Pillow encoding) runs inside
``asyncio.to_thread`` so the FastAPI event loop keeps serving the polling
endpoints while the background task advances.  No FITS is downloaded twice:
Elide already downloaded the cutouts when building the ``Observation`` objects.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, List, Optional, Sequence
from uuid import UUID

import numpy as np
from astropy.visualization import AsinhStretch, ZScaleInterval
from PIL import Image

from app.storage.base import ISessionRepository
from app.storage.factory import SessionRepositoryFactory
from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)

#: Longest side of the generated preview, in pixels (small enough for the API).
PREVIEW_MAX_SIZE_PX = 512

PathLike = Any  # str | Path

_ESTADO_EN_PROCESO = "EN_PROCESO"
_ESTADO_FALLIDO = "FALLIDO"


def _safe_stem(obs_id: str) -> str:
    """Sanitize an observation id so it can only name a file inside ``images_dir``."""
    stem = str(obs_id).replace("/", "_").replace("\\", "_").replace("..", "_").strip()
    return stem or "observation"


def render_preview_png(
    image: np.ndarray,
    output_path: PathLike,
    *,
    max_size_px: int = PREVIEW_MAX_SIZE_PX,
) -> Path:
    """Stretch a FITS matrix and write an 8-bit PNG preview.

    The stretch is ``ZScaleInterval`` (robust limits) followed by
    ``AsinhStretch`` (keeps faint structure visible), the standard recipe for
    astronomical quick-looks. Non-finite pixels are replaced by the median of
    the finite ones so NaNs do not poison the limits.
    """
    data = np.asarray(image, dtype=np.float64)
    if data.ndim != 2 or data.size == 0:
        raise ValueError(f"image must be a non-empty 2-D array, got shape {data.shape}")

    finite = np.isfinite(data)
    if not finite.any():
        raise ValueError("image contains no finite pixels to stretch")

    finite_values = data[finite]
    data = np.where(finite, data, float(np.median(finite_values)))

    vmin, vmax = ZScaleInterval().get_limits(data)
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmax <= vmin:
        vmin = float(finite_values.min())
        vmax = float(finite_values.max())

    if vmax <= vmin:
        stretched = np.zeros(data.shape, dtype=np.float64)
    else:
        normalized = np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
        stretched = AsinhStretch()(normalized)

    pixels = np.clip(stretched * 255.0, 0.0, 255.0).astype(np.uint8)
    # FITS rows are stored bottom-up; flip so the preview is north-up like an image.
    # ``flipud`` returns a negative-stride view, so force a contiguous buffer for PIL.
    preview = Image.fromarray(np.ascontiguousarray(np.flipud(pixels)))
    preview.thumbnail((max_size_px, max_size_px))

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview.save(destination, format="PNG", optimize=True)
    return destination


async def _update_session(
    repository: ISessionRepository,
    session_id: UUID,
    *,
    processed: int,
    rendered: int,
    total: int,
    errors: Sequence[str],
    estado: Optional[str] = None,
) -> None:
    """Read-modify-write the session document with the current preview progress."""
    session = await repository.get_by_id(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found in the repository")

    if estado is not None:
        session["estado"] = estado
    session["total_observaciones_grupo"] = int(
        session.get("total_observaciones_grupo") or total
    )
    session["observaciones_descargadas"] = rendered
    session["progreso_porcentaje"] = (
        round(processed / total * 100.0, 2) if total else 0.0
    )
    session["error_detail"] = "; ".join(errors) if errors else None
    await repository.save(session)


async def process_background_group(
    session_id: UUID,
    observations: Sequence[Observation],
    images_dir: PathLike,
) -> None:
    """Render one PNG preview per in-memory ``Observation`` in the background.

    Args:
        session_id: Session identifier used to persist progress.
        observations: ``Observation`` objects already built by Elide (each one
            carries its ``.image`` NumPy matrix).  Every observation yields one
            preview named ``<obs_id>.png``.
        images_dir: Directory where the PNG previews are written.

    The session document is updated after every record, so ``GET
    /analysis/{id}`` reports ``observaciones_descargadas`` and
    ``progreso_porcentaje`` while the group is still rendering. A failing
    record is logged, recorded in ``error_detail`` and does not abort the
    remaining renders; the session is only marked ``FALLIDO`` when no preview
    could be produced. Completion is left to the next phase (motion
    analysis), which owns the terminal state.
    """
    group = list(observations)
    if not group:
        LOGGER.warning("Session %s has no observations to render", session_id)
        return

    images_path = Path(images_dir)
    repository = SessionRepositoryFactory.get_repository()
    total = len(group)

    processed = 0
    rendered = 0
    errors: List[str] = []
    await _update_session(
        repository,
        session_id,
        processed=processed,
        rendered=rendered,
        total=total,
        errors=errors,
        estado=_ESTADO_EN_PROCESO,
    )

    for observation in group:
        obs_id = str(observation.id)
        try:
            png_path = await asyncio.to_thread(
                render_preview_png, observation.image, images_path / f"{_safe_stem(obs_id)}.png"
            )
            LOGGER.info("Preview written for %s at %s", obs_id, png_path)
        except Exception as exc:  # noqa: BLE001 - one bad record must not kill the group
            LOGGER.warning("Render failed for %s: %s", obs_id, exc)
            errors.append(f"{obs_id}: {exc}")
        else:
            rendered += 1
            LOGGER.info("Rendered %s (%s/%s)", obs_id, rendered, total)
        finally:
            # Progress tracks terminal observations (ready or failed), so the
            # bar never stalls on a failed record.
            processed += 1
            await _update_session(
                repository,
                session_id,
                processed=processed,
                rendered=rendered,
                total=total,
                errors=errors,
            )

    if rendered == 0:
        await _update_session(
            repository,
            session_id,
            processed=total,
            rendered=0,
            total=total,
            errors=errors,
            estado=_ESTADO_FALLIDO,
        )
        LOGGER.error("No preview could be produced for session %s", session_id)
