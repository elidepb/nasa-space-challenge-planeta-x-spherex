"""Background FITS download and preview rendering for one spectral group (S8).

The service consumes the metadata records produced by
``app.services.catalog_service.fetch_phase1_metadata``, downloads (or reuses) the
SPHEREx FITS file of each record, reads its science matrix and writes a
contrast-stretched PNG preview into the images volume.

Everything that is CPU/IO bound (network download, FITS parsing, NumPy
statistics and Pillow encoding) runs inside ``asyncio.to_thread`` so the
FastAPI event loop keeps serving the polling endpoints while the background
task advances.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Sequence, Tuple, Union
from uuid import UUID

import numpy as np
from astropy.visualization import AsinhStretch, ZScaleInterval
from PIL import Image

from app.storage.base import ISessionRepository
from app.storage.factory import SessionRepositoryFactory
from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.irsa import IrsaRecord, download_record

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime import cycle
    from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)

#: Longest side of the generated preview, in pixels (small enough for the API).
PREVIEW_MAX_SIZE_PX = 512

PathLike = Union[str, Path]

_ESTADO_EN_PROCESO = "EN_PROCESO"
_ESTADO_FALLIDO = "FALLIDO"

_OBS_ID_KEYS = ("obs_id", "id", "observation_id")


def _optional_float(value: Any) -> Optional[float]:
    """Coerce ``value`` to a finite float, returning ``None`` when impossible."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    """Return the first non-empty value found for ``keys`` in ``record``."""
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _record_label(record: Mapping[str, Any]) -> str:
    """Human readable identifier used in logs and error messages."""
    label = _first_present(record, *_OBS_ID_KEYS)
    if label is None:
        label = _first_present(record, "fits_source", "access_url")
    return str(label) if label is not None else "<unknown record>"


def _record_obs_id(
    record: Mapping[str, Any], irsa_record: Optional[IrsaRecord]
) -> Optional[str]:
    """Resolve the observation id from the record, falling back to the FITS source."""
    value = _first_present(record, *_OBS_ID_KEYS)
    if value is not None:
        return str(value)
    if irsa_record is not None and irsa_record.obs_id:
        return str(irsa_record.obs_id)
    fits_source = _first_present(record, "fits_source")
    if fits_source is not None:
        # FITS sources may carry a query string (cutout URLs); keep only the stem.
        return Path(str(fits_source).split("?")[0]).stem or None
    return None


def _safe_stem(obs_id: str) -> str:
    """Sanitize an observation id so it can only name a file inside ``images_dir``."""
    stem = str(obs_id).replace("/", "_").replace("\\", "_").replace("..", "_").strip()
    return stem or "observation"


def _existing_local_fits(record: Mapping[str, Any]) -> Optional[Path]:
    """Return the record's ``fits_source`` when it already points to a local FITS."""
    fits_source = _first_present(record, "fits_source")
    if fits_source is None:
        return None
    candidate = Path(str(fits_source))
    return candidate if candidate.is_file() else None


def _as_irsa_record(record: Mapping[str, Any]) -> IrsaRecord:
    """Adapt a metadata dict to the ``IrsaRecord`` expected by ``download_record``."""
    access_url = _first_present(record, "access_url", "fits_source")
    if access_url is None:
        raise ValueError(
            f"Record {_record_label(record)} has neither 'access_url' nor 'fits_source'"
        )
    cutout_url = _first_present(record, "cutout_url") or access_url
    bandpass = _first_present(record, "bandpass")
    return IrsaRecord(
        access_url=str(access_url),
        cutout_url=str(cutout_url),
        time_mjd=_optional_float(_first_present(record, "time_mjd")),
        bandpass=str(bandpass) if bandpass is not None else None,
        obs_id=_record_obs_id(record, None),
    )


def _read_observation(
    record: Mapping[str, Any], cache_dir: Path
) -> Tuple["Observation", str]:
    """Blocking step: resolve the FITS file, read it and return ``(observation, obs_id)``.

    A record whose ``fits_source`` already exists on disk (cached FITS or a local
    path) is read directly; every other record goes through the Elide downloader.
    """
    local_path = _existing_local_fits(record)
    irsa_record: Optional[IrsaRecord] = None
    download_url: Optional[str] = None
    if local_path is not None:
        fits_path = local_path
    else:
        irsa_record = _as_irsa_record(record)
        downloaded = download_record(irsa_record, cache_dir=cache_dir)
        fits_path = Path(downloaded.path)
        download_url = downloaded.url

    extra_metadata: dict[str, Any] = {}
    if irsa_record is not None:
        if irsa_record.bandpass:
            extra_metadata["bandpass"] = irsa_record.bandpass
        extra_metadata["access_url"] = irsa_record.access_url
        extra_metadata["cutout_url"] = irsa_record.cutout_url
    if download_url:
        extra_metadata["download_url"] = download_url

    obs_id = _record_obs_id(record, irsa_record)
    observation = observation_from_fits(
        fits_path,
        observation_id=obs_id,
        ra=_optional_float(_first_present(record, "ra")),
        dec=_optional_float(_first_present(record, "dec")),
        timestamp_mjd=_optional_float(_first_present(record, "time_mjd")),
        wavelength_fallback=_optional_float(
            _first_present(record, "wavelength", "wavelength_um")
        ),
        extra_metadata=extra_metadata,
    )
    return observation, obs_id or observation.id


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


def _download_and_render_record(
    record: Mapping[str, Any], cache_dir: Path, images_dir: Path
) -> Tuple[str, Path]:
    """Blocking step for one record: download/read the FITS and render its preview."""
    observation, obs_id = _read_observation(record, cache_dir)
    png_path = images_dir / f"{_safe_stem(obs_id)}.png"
    render_preview_png(observation.image, png_path)
    LOGGER.info("Preview written for %s at %s", obs_id, png_path)
    return obs_id, png_path


async def _update_session(
    repository: ISessionRepository,
    session_id: UUID,
    *,
    processed: int,
    downloaded: int,
    total: int,
    errors: Sequence[str],
    estado: Optional[str] = None,
) -> None:
    """Read-modify-write the session document with the current download progress."""
    session = await repository.get_by_id(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found in the repository")

    if estado is not None:
        session["estado"] = estado
    session["total_observaciones_grupo"] = int(
        session.get("total_observaciones_grupo") or total
    )
    session["observaciones_descargadas"] = downloaded
    session["progreso_porcentaje"] = (
        round(processed / total * 100.0, 2) if total else 0.0
    )
    session["error_detail"] = "; ".join(errors) if errors else None
    await repository.save(session)


async def process_background_group(
    session_id: UUID,
    records: Sequence[Mapping[str, Any]],
    cache_dir: PathLike,
    images_dir: PathLike,
) -> None:
    """Download a spectral group in the background and render one PNG per record.

    Args:
        session_id: Session identifier used to persist progress.
        records: Metadata dicts from ``fetch_phase1_metadata`` (``obs_id``,
            ``fits_source``, ``access_url``, ``cutout_url``, ``time_mjd``,
            ``bandpass``, ...). Every record yields one preview.
        cache_dir: Directory where Elide caches the downloaded FITS files.
        images_dir: Directory where ``<obs_id>.png`` previews are written.

    The session document is updated after every record, so ``GET
    /analysis/{id}`` reports ``observaciones_descargadas`` and
    ``progreso_porcentaje`` while the group is still downloading. A failing
    record is logged, recorded in ``error_detail`` and does not abort the
    remaining downloads; the session is only marked ``FALLIDO`` when no
    preview could be produced. Completion is left to the next phase (motion
    analysis), which owns the terminal state.
    """
    group = list(records)
    if not group:
        LOGGER.warning("Session %s has no records to download", session_id)
        return

    cache_path = Path(cache_dir)
    images_path = Path(images_dir)
    repository = SessionRepositoryFactory.get_repository()
    total = len(group)

    processed = 0
    downloaded = 0
    errors: List[str] = []
    await _update_session(
        repository,
        session_id,
        processed=processed,
        downloaded=downloaded,
        total=total,
        errors=errors,
        estado=_ESTADO_EN_PROCESO,
    )

    for record in group:
        label = _record_label(record)
        try:
            obs_id, _png_path = await asyncio.to_thread(
                _download_and_render_record, record, cache_path, images_path
            )
        except Exception as exc:  # noqa: BLE001 - one bad record must not kill the group
            LOGGER.warning("Download/render failed for %s: %s", label, exc)
            errors.append(f"{label}: {exc}")
        else:
            downloaded += 1
            LOGGER.info("Downloaded %s (%s/%s)", obs_id, downloaded, total)
        finally:
            # Progress tracks terminal observations (ready or failed), like the
            # domain aggregate, so the bar never stalls on a failed record.
            processed += 1
            await _update_session(
                repository,
                session_id,
                processed=processed,
                downloaded=downloaded,
                total=total,
                errors=errors,
            )

    if downloaded == 0:
        await _update_session(
            repository,
            session_id,
            processed=total,
            downloaded=0,
            total=total,
            errors=errors,
            estado=_ESTADO_FALLIDO,
        )
        LOGGER.error("No preview could be produced for session %s", session_id)
