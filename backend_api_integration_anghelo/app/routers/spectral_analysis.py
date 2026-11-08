"""FastAPI router for spectral analysis orchestration (7 endpoints + FITS download).

Connects the Elide catalog/download services, the Etner motion engine and the
SessionRepositoryFactory. CPU/IO-bound work (download, PNG render, Etner) runs
through ``asyncio.to_thread`` so the polling endpoints stay responsive.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path as PathParam
from fastapi.responses import Response

from app.core.cache import ensure_data_volumes
from app.core.config import settings
from app.schemas.requests import AnalysisCreateRequest, RGBCompositeRequest
from app.schemas.responses import (
    AnalysisResponse,
    CandidateResponse,
    ImageListItemSchema,
    ImageListResponse,
    ObservationSummarySchema,
    SessionStatusResponse,
)
from app.services.catalog_service import fetch_phase1_metadata
from app.services.download_service import process_background_group
from app.services.motion_service import run_etner_analysis
from app.services.rgb_service import generate_rgb_png
from app.storage.factory import SessionRepositoryFactory
from spherex_pipeline.fits_reader import observation_from_fits

router = APIRouter(tags=["spectral analyses"])

# In-memory store of Observation objects per session, keyed by obs_id.
# Used by the RGB composite and motion endpoints. Matrices never leave this
# process; only small previews are written to the images volume.
_OBSERVATION_STORE: dict[UUID, dict[str, Any]] = {}


def _session_dirs(session_id: UUID) -> tuple[Path, Path]:
    cache_dir = Path(settings.CACHE_DIR)
    images_dir = Path(settings.IMAGES_DIR)
    return cache_dir, images_dir


def _store_observations(
    session_id: UUID,
    records: list[dict],
    ra: float,
    dec: float,
    cache_dir: Path,
) -> dict[str, Any]:
    """Rehydrate Observation objects from locally cached FITS files."""
    store: dict[str, Any] = {}
    for record in records:
        fits_source = record.get("fits_source")
        obs_id = record.get("obs_id")
        if not obs_id or not fits_source:
            continue
        candidate = Path(str(fits_source))
        if not candidate.is_file():
            continue
        try:
            obs = observation_from_fits(
                candidate,
                observation_id=str(obs_id),
                ra=ra,
                dec=dec,
                timestamp_mjd=record.get("time_mjd"),
                wavelength_fallback=record.get("wavelength"),
                extra_metadata={
                    "bandpass": record.get("bandpass"),
                    "survey_index": record.get("survey_index"),
                    "source": record.get("source", "irsa"),
                    "local_path": str(candidate),
                },
            )
            store[str(obs_id)] = obs
        except Exception:  # noqa: BLE001 - one bad frame must not break the session
            continue
    return store


async def _run_phase2(
    session_id: UUID,
    records: list[dict],
    ra: float,
    dec: float,
    cache_dir: Path,
    images_dir: Path,
) -> None:
    """Background Phase 2: download, render previews, then run Etner analysis."""
    repository = SessionRepositoryFactory.get_repository()

    # Phase 2a: download + render previews.
    await process_background_group(
        session_id=session_id,
        records=records,
        cache_dir=cache_dir,
        images_dir=images_dir,
    )

    # Phase 2b: rehydrate observations in memory for RGB / motion endpoints.
    observations = _store_observations(session_id, records, ra, dec, cache_dir)
    _OBSERVATION_STORE[session_id] = observations

    # Phase 2c: Etner motion analysis when at least two frames are ready.
    session = await repository.get_by_id(session_id)
    if session is None:
        return
    session["estado"] = "COMPLETADO"
    session["progreso_porcentaje"] = 100.0
    session["observaciones_descargadas"] = len(records)
    try:
        result = await asyncio.to_thread(
            run_etner_analysis, list(observations.values())
        )
        session["candidatos_detectados"] = len(result.get("candidates", []) or [])
    except Exception as exc:  # noqa: BLE001 - motion failure must not block delivery
        session["error_detail"] = f"motion analysis: {exc}"
    await repository.save(session)


@router.post(
    "/spectral-analyses",
    status_code=202,
    response_model=AnalysisResponse,
    summary="Iniciar análisis espectral (Fase 1)",
)
async def start_spectral_analysis(
    background_tasks: BackgroundTasks,
    request: AnalysisCreateRequest,
) -> AnalysisResponse:
    """Ejecuta la consulta TAP de IRSA para un grupo espectral y encola la Fase 2."""
    ensure_data_volumes()

    records = fetch_phase1_metadata(
        ra=request.ra,
        dec=request.dec,
        size_deg=request.size_deg,
        bandpass=request.bandpass,
        spectral_group=request.spectral_group,
        cache_dir=settings.CACHE_DIR,
    )

    session_id = uuid.uuid4()
    repository = SessionRepositoryFactory.get_repository()
    await repository.save(
        {
            "session_id": session_id,
            "estado": "EN_PROCESO",
            "message": f"Metadatos obtenidos. Descarga en segundo plano de {len(records)} observaciones iniciada.",
            "spectral_group": request.spectral_group,
            "ra": request.ra,
            "dec": request.dec,
            "total_observaciones_grupo": len(records),
            "observaciones_descargadas": 0,
            "progreso_porcentaje": 0.0,
            "candidatos_detectados": 0,
            "error_detail": None,
        }
    )

    background_tasks.add_task(
        _run_phase2,
        session_id,
        records,
        request.ra,
        request.dec,
        Path(settings.CACHE_DIR),
        Path(settings.IMAGES_DIR),
    )
    _session_dirs(session_id)  # noqa: B018 - ensures per-run volume dirs exist

    observaciones = [
        ObservationSummarySchema(
            id=r["obs_id"],
            timestamp=r["timestamp"],
            detector=r["detector"],
            wavelength=r["wavelength"],
            bandwidth=r["bandwidth"],
            fits_source=r["fits_source"],
            shape=r["shape"],
            n_invalid_pixels=r["n_invalid_pixels"],
        )
        for r in records
    ]
    return AnalysisResponse(
        session_id=session_id,
        estado="EN_PROCESO",
        message=f"Metadatos obtenidos. Descarga en segundo plano de {len(records)} observaciones iniciada.",
        spectral_group=request.spectral_group,
        observaciones=observaciones,
    )


@router.get(
    "/spectral-analyses/{session_id}",
    response_model=SessionStatusResponse,
    summary="Consultar estado de sesión",
)
async def get_session_status(
    session_id: UUID = PathParam(..., description="Identificador único de la sesión"),
) -> SessionStatusResponse:
    repository = SessionRepositoryFactory.get_repository()
    session = await repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStatusResponse(
        session_id=session["session_id"],
        estado=session.get("estado", "EN_PROCESO"),
        progreso_porcentaje=float(session.get("progreso_porcentaje", 0.0)),
        total_observaciones_grupo=int(session.get("total_observaciones_grupo", 0)),
        observaciones_descargadas=int(session.get("observaciones_descargadas", 0)),
        candidatos_detectados=int(session.get("candidatos_detectados", 0)),
        error_detail=session.get("error_detail"),
    )


@router.get(
    "/spectral-analyses/{session_id}/observations",
    response_model=list[ObservationSummarySchema],
    summary="Resumen de observaciones (sin matrices)",
)
async def list_observations(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
) -> list[ObservationSummarySchema]:
    repository = SessionRepositoryFactory.get_repository()
    session = await repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    records = session.get("observaciones", [])
    return [
        ObservationSummarySchema(
            id=r["obs_id"],
            timestamp=r["timestamp"],
            detector=r["detector"],
            wavelength=r["wavelength"],
            bandwidth=r["bandwidth"],
            fits_source=r["fits_source"],
            shape=r["shape"],
            n_invalid_pixels=r["n_invalid_pixels"],
        )
        for r in records
    ]


@router.get(
    "/spectral-analyses/{session_id}/images",
    response_model=ImageListResponse,
    summary="Lista de imágenes disponibles y URLs de descarga",
)
async def list_images(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
) -> ImageListResponse:
    repository = SessionRepositoryFactory.get_repository()
    session = await repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    records = session.get("observaciones", [])
    items = []
    for r in records:
        obs_id = r["obs_id"]
        items.append(
            ImageListItemSchema(
                obs_id=obs_id,
                survey_index=int(r.get("survey_index") or 1),
                wavelength_um=float(r["wavelength"]) if r.get("wavelength") is not None else 0.0,
                shape=r["shape"] or [0, 0],
                preview_png_url=(
                    f"/api/v1/spectral-analyses/{session_id}/images/{obs_id}/preview.png"
                ),
                fits_download_url=(
                    f"/api/v1/spectral-analyses/{session_id}/images/{obs_id}/file.fits"
                ),
            )
        )
    return ImageListResponse(
        session_id=session_id,
        total_imagenes=len(items),
        imagenes=items,
    )


@router.get(
    "/spectral-analyses/{session_id}/images/{obs_id}/preview.png",
    summary="Servidor de previsualización PNG astronómica",
)
async def get_preview_png(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
    obs_id: str = PathParam(..., description="ID de la observación"),
) -> Response:
    images_dir = Path(settings.IMAGES_DIR)
    png_path = images_dir / f"{obs_id}.png"
    if not png_path.is_file():
        raise HTTPException(status_code=404, detail="Preview not found")
    data = png_path.read_bytes()
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.get(
    "/spectral-analyses/{session_id}/images/{obs_id}/file.fits",
    summary="Descarga del FITS original de una observación",
)
async def get_fits_file(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
    obs_id: str = PathParam(..., description="ID de la observación"),
) -> Response:
    repository = SessionRepositoryFactory.get_repository()
    session = await repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    cache_dir = Path(settings.CACHE_DIR)
    # Locate the FITS by matching obs_id against stored records.
    fits_path: Path | None = None
    for r in session.get("observaciones", []):
        if r.get("obs_id") == obs_id:
            candidate = Path(str(r.get("fits_source", "")))
            if candidate.is_file():
                fits_path = candidate
                break
    if fits_path is None:
        raise HTTPException(status_code=404, detail="FITS file not found")
    data = fits_path.read_bytes()
    return Response(
        content=data,
        media_type="application/fits",
        headers={"Content-Disposition": f'attachment; filename="{obs_id}.fits"'},
    )


@router.post(
    "/spectral-analyses/{session_id}/rgb-composite",
    summary="Composición falso color RGB",
)
async def rgb_composite(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
    request: RGBCompositeRequest = ...,
) -> Response:
    store = _OBSERVATION_STORE.get(session_id)
    if not store:
        raise HTTPException(status_code=404, detail="Session observations not ready")
    missing = [
        channel
        for channel, obs_id in (
            ("red", request.red_obs_id),
            ("green", request.green_obs_id),
            ("blue", request.blue_obs_id),
        )
        if obs_id not in store
    ]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Observations not available for channel(s): {', '.join(missing)}",
        )
    observations = [
        store[request.red_obs_id],
        store[request.green_obs_id],
        store[request.blue_obs_id],
    ]
    try:
        png_bytes = await asyncio.to_thread(
            generate_rgb_png, observations
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=png_bytes, media_type="image/png")


@router.get(
    "/spectral-analyses/{session_id}/candidates",
    response_model=CandidateResponse,
    summary="Candidatos de movimiento astronómico (Etner)",
)
async def get_candidates(
    session_id: UUID = PathParam(..., description="Identificador de sesión"),
) -> CandidateResponse:
    repository = SessionRepositoryFactory.get_repository()
    session = await repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("estado") != "COMPLETADO":
        raise HTTPException(
            status_code=400,
            detail="Candidates are only available when estado == COMPLETADO",
        )
    store = _OBSERVATION_STORE.get(session_id, {})
    observations = list(store.values())
    result = await asyncio.to_thread(
        motion_service.run_etner_analysis, observations
    )
    candidates = result.get("candidates", []) or []
    return CandidateResponse(
        session_id=session_id,
        total_candidatos=len(candidates),
        candidatos=[
            {
                "candidate_id": c.get("id", f"cand_{i:03d}"),
                "ra": c.get("ra"),
                "dec": c.get("dec"),
                "snr": c.get("snr"),
                "motion_arcsec_yr": c.get("motionArcsecPerYear"),
                "status": c.get("status", "VALIDATED"),
            }
            for i, c in enumerate(candidates, start=1)
        ],
    )
