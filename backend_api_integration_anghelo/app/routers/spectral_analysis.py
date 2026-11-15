"""FastAPI router for spectral analysis orchestration (7 endpoints + FITS download).

Connects the Elide catalog/download services, the Etner motion engine and the
SessionRepositoryFactory. CPU/IO-bound work (download, PNG render, Etner) runs
through ``asyncio.to_thread`` so the polling endpoints stay responsive.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
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
    CandidatePairResult,
    CandidateResponse,
    ImageListItemSchema,
    ImageListResponse,
    ObservationSummarySchema,
    SessionStatusResponse,
)
from astropy.time import Time
from spherex_pipeline.irsa import dedupe_records, query_observations
from spherex_pipeline.spectral_select import (
    bin_records_by_surveys,
    get_detector_bins,
    split_records_into_surveys,
)

from app.services.catalog_service import fetch_phase1_metadata_and_observations
from app.services.download_service import process_background_group
from app.services.motion_service import run_etner_analysis
from app.services.rgb_service import (
    generate_rgb_composites_by_survey,
    generate_rgb_png,
)
from app.storage.factory import SessionRepositoryFactory

router = APIRouter(tags=["spectral analyses"])


def _read_wavelength_real(fits_source: str | None) -> float | None:
    """Lee la longitud de onda real del header FITS local (sin descargar nada).

    Intenta varias claves comunes de cabecera FITS. Devuelve None si el archivo
    no existe localmente, no se puede leer o no tiene ninguna de las claves.
    """
    if not fits_source or str(fits_source).startswith("http"):
        return None
    try:
        if not Path(fits_source).exists():
            return None
        with fits.open(fits_source, memmap=False) as hdul:
            hdr = hdul[0].header
            for key in ("CRVAL1W", "CRVAL3", "WAVELEN", "RESTWAV", "CRVAL1", "OBSWAV"):
                val = hdr.get(key)
                if val is not None:
                    return float(val)
    except Exception:
        return None
    return None


# In-memory store of Observation objects per session, keyed by obs_id.
# Used by the RGB composite and motion endpoints. Matrices never leave this
# process; only small previews are written to the images volume.
_OBSERVATION_STORE: dict[UUID, dict[str, Any]] = {}


async def _run_phase2(
    session_id: UUID,
    observations: list[Any],
    images_dir: Path,
) -> None:
    """Background Phase 2: render previews, then run Etner analysis.

    ``observations`` are the ``Observation`` objects Elide already built during
    Phase 1 (each one carries its ``.image`` NumPy matrix), so no FITS is
    downloaded twice.
    """
    repository = SessionRepositoryFactory.get_repository()

    # Phase 2a: render previews from the in-memory matrices.
    await process_background_group(
        session_id=session_id,
        observations=observations,
        images_dir=images_dir,
    )

    # Phase 2b: keep the observations in memory for RGB / motion endpoints.
    store = {str(obs.id): obs for obs in observations}
    _OBSERVATION_STORE[session_id] = store

    # Phase 2c: Etner motion analysis when at least two frames are ready.
    session = await repository.get_by_id(session_id)
    if session is None:
        return
    session["estado"] = "COMPLETADO"
    session["progreso_porcentaje"] = 100.0
    session["observaciones_descargadas"] = len(observations)
    try:
        result = await asyncio.to_thread(
            run_etner_analysis, list(store.values())
        )
        session["candidatos_detectados"] = len(result.get("candidates", []) or [])
    except Exception as exc:  # noqa: BLE001 - motion failure must not block delivery
        session["error_detail"] = f"motion analysis: {exc}"
    await repository.save(session)


@router.post(
    "/spectral-analyses",
    status_code=202,
    response_model=AnalysisResponse,
    response_model_exclude_none=True,
    summary="Iniciar análisis espectral (Fase 1)",
)
async def start_spectral_analysis(
    background_tasks: BackgroundTasks,
    request: AnalysisCreateRequest,
) -> AnalysisResponse:
    """Valida la petición, consulta metadatos rápidos de IRSA y encola el procesamiento completo.

    Los metadatos rápidos (sin descargar FITS completos) se devuelven inmediatamente
    en la respuesta 202. La descarga completa de FITS y el análisis de movimiento
    se ejecutan en segundo plano; consulte el progreso con
    ``GET /spectral-analyses/{session_id}``.
    """
    ensure_data_volumes()

    session_id = uuid.uuid4()
    repository = SessionRepositoryFactory.get_repository()
    await repository.save(
        {
            "session_id": session_id,
            "estado": "EN_PROCESO",
            "message": "Consultando metadatos de IRSA...",
            "spectral_group": request.spectral_group,
            "survey_index": request.spectral_group,
            "bandpass": request.bandpass,
            "ra": request.ra,
            "dec": request.dec,
            "total_observaciones_grupo": 0,
            "observaciones_descargadas": 0,
            "progreso_porcentaje": 0.0,
            "candidatos_detectados": 0,
            "error_detail": None,
        }
    )

    # Consulta rápida de metadatos sin descargar FITS completos (TAP/SIA ligero).
    try:
        raw_records = await asyncio.to_thread(
            query_observations,
            request.ra,
            request.dec,
            request.size_deg,
            qr="qr2",
            bandpass=request.bandpass,
        )
        unique_records, _ = await asyncio.to_thread(dedupe_records, raw_records)
    except Exception:
        unique_records = []

    # Separación espectro-temporal (igual que el background task): partición en
    # surveys por gaps >45 días, luego 17 bins por posición relativa y selección
    # solo del grupo espectral solicitado. Sin descargar FITS completos.
    all_bins = get_detector_bins(request.bandpass, n_bins=17)
    surveys_tap = split_records_into_surveys(unique_records, gap_days=45.0)
    binned_records, _ = bin_records_by_surveys(all_bins, surveys_tap)
    matched_records = binned_records[request.spectral_group - 1]

    observaciones_rapidas = [
        ObservationSummarySchema(
            id_exposicion=(rec.obs_id or f"obs_{i + 1}"),
            timestamp=(
                Time(float(rec.time_mjd), format="mjd").iso
                if rec.time_mjd is not None
                else "n/d"
            ),
            survey_index=s_idx,
            wavelength=wl,
            fits_source=rec.access_url,
        )
        for i, (rec, wl, s_idx) in enumerate(matched_records)
    ]

    # Guarda los metadatos rápidos en la sesión para que GET /observations y
    # GET /images ya tengan datos antes de que termine la descarga completa.
    session = await repository.get_by_id(session_id)
    if session is not None:
        session["observaciones"] = [o.model_dump() for o in observaciones_rapidas]
        session["total_observaciones_grupo"] = len(observaciones_rapidas)
        session["message"] = (
            f"Metadatos rápidos obtenidos para {len(observaciones_rapidas)} observaciones. "
            "Descargando en segundo plano."
        )
        await repository.save(session)

    # Lanzar proceso completo en segundo plano (descarga FITS + Phase 2 + Etner).
    background_tasks.add_task(
        _process_phase1_background,
        session_id,
        request,
        settings,
    )

    return AnalysisResponse(
        session_id=session_id,
        estado="EN_PROCESO",
        message=(
            f"Metadatos rápidos obtenidos para {len(observaciones_rapidas)} observaciones. "
            "Procesamiento completo en segundo plano."
        ),
        spectral_group=request.spectral_group,
        observaciones=observaciones_rapidas,
    )


async def _process_phase1_background(
    session_id: UUID,
    request: AnalysisCreateRequest,
    settings: Any,
) -> None:
    """Descarga FITS completos de Elide en segundo plano, luego ejecuta Fase 2.

    Actualiza la sesión con los metadatos completos (shape, n_invalid_pixels, etc.)
    una vez que la descarga termina.
    """
    try:
        records, observations = await asyncio.to_thread(
            fetch_phase1_metadata_and_observations,
            ra=request.ra,
            dec=request.dec,
            size_deg=request.size_deg,
            bandpass=request.bandpass,
            spectral_group=request.spectral_group,
            cache_dir=settings.CACHE_DIR,
        )

        repository = SessionRepositoryFactory.get_repository()
        session = await repository.get_by_id(session_id)
        if session is not None:
            # Enriquece cada registro con la longitud de onda real del header FITS
            # local (ya descargado por el background task).
            for r in records:
                r["wavelength_real"] = _read_wavelength_real(r.get("fits_source"))

            session["observaciones"] = records
            session["total_observaciones_grupo"] = len(records)
            session["message"] = f"Metadatos completos obtenidos. Procesando {len(records)} observaciones en segundo plano."
            await repository.save(session)

        # Almacena los objetos Observation en memoria para RGB y Etner.
        store = {str(r["obs_id"]): obs for r, obs in zip(records, observations)}
        _OBSERVATION_STORE[session_id] = store

        await _run_phase2(session_id, observations, Path(settings.IMAGES_DIR))
    except Exception as exc:  # noqa: BLE001 - no dejar la sesión colgada sin error
        repository = SessionRepositoryFactory.get_repository()
        session = await repository.get_by_id(session_id)
        if session is not None:
            session["estado"] = "ERROR"
            session["error_detail"] = str(exc)
            await repository.save(session)


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
    survey_index = int(session.get("survey_index") or 1)
    return [
        ObservationSummarySchema(
            id_exposicion=r.get("id_exposicion") or r.get("obs_id", "desconocido"),
            timestamp=r["timestamp"],
            survey_index=int(r.get("survey_index") or survey_index),
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
        obs_id = r.get("id_exposicion") or r.get("obs_id", "desconocido")
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
        if r.get("id_exposicion") == obs_id or r.get("obs_id") == obs_id:
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
    "/spectral-analyses/rgb-composite",
    summary="Composición falso color RGB por survey (una imagen por época)",
)
async def rgb_composite(
    request: RGBCompositeRequest = ...,
) -> dict[str, Any]:
    """Genera una composición RGB falsa por survey (época).

    Para cada canal (red/green/blue) consulta Elide con el detector
    ``SPHEREx-D{sensor}`` y el grupo espectral pedido, agrupa las observaciones
    en surveys (gaps temporales > 45 días) y arma un PNG RGB por survey común
    a los tres canales. Cada PNG se persiste en el volumen de imágenes y se
    sirve mediante ``GET /spectral-analyses/rgb-composites/{composite_id}.png``.
    """
    channels = [
        {"channel": ch.channel, "sensor": ch.sensor, "group": ch.group}
        for ch in request.channels
    ]

    try:
        result = await generate_rgb_composites_by_survey(
            request.ra,
            request.dec,
            request.size_deg,
            channels,
            settings.CACHE_DIR,
            settings.IMAGES_DIR,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, TimeoutError) as exc:
        # Fallos de red/timeout consultando IRSA (Elide): no es un error del
        # cliente, es una dependencia externa no disponible. Devuelve 502 en
        # lugar de dejar que suba como 500 Internal Server Error.
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo consultar IRSA para generar el RGB: {exc}",
        )
    return result


@router.get(
    "/spectral-analyses/rgb-composites/{composite_id}.png",
    summary="Descarga del PNG de una composición RGB por survey",
)
async def get_rgb_composite_png(
    composite_id: str = PathParam(..., description="Identificador de la composición"),
) -> Response:
    images_dir = Path(settings.IMAGES_DIR)
    png_path = images_dir / f"{composite_id}.png"
    if not png_path.is_file():
        raise HTTPException(status_code=404, detail="Composite PNG not found")
    data = png_path.read_bytes()
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


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

    # Agrupa observaciones por survey_index para hacer pares consecutivos:
    # 3 surveys → pares (1,2) y (2,3); 4 surveys → (1,2), (2,3), (3,4).
    by_survey: dict[int, list[Any]] = defaultdict(list)
    for obs in store.values():
        s_idx = int(obs.metadata.get("survey_index", 1))
        by_survey[s_idx].append(obs)

    survey_ids = sorted(by_survey.keys())
    pairs = [(survey_ids[i], survey_ids[i + 1]) for i in range(len(survey_ids) - 1)]

    async def analyze_pair(s1: int, s2: int) -> tuple[int, int, dict]:
        obs_pair = by_survey[s1] + by_survey[s2]
        result = await asyncio.to_thread(run_etner_analysis, obs_pair)
        return s1, s2, result

    pair_results = await asyncio.gather(
        *[analyze_pair(a, b) for a, b in pairs]
    )

    total_candidatos = 0
    pair_schemas = []
    for s1, s2, result in pair_results:
        candidates = result.get("candidates", []) or []
        total_candidatos += len(candidates)
        pair_schemas.append(
            CandidatePairResult(
                survey_pair=[s1, s2],
                total_candidatos=len(candidates),
                candidatos=[
                    {
                        "candidate_id": c.get("id", f"cand_{i:03d}"),
                        "ra": c.get("ra"),
                        "dec": c.get("dec"),
                        "snr": c.get("snr"),
                        "motion_arcsec_yr": c.get("motionArcsecPerYear"),
                        "displacement_arcsec": c.get("displacementArcsec"),
                        "status": c.get("status", "VALIDATED"),
                        # Etner ya entrega detections con x/y en píxeles; el front las usa
                        # para marcar el cielo. Sin esto la UI no tiene anclas.
                        "detections": c.get("detections") or [],
                    }
                    for i, c in enumerate(candidates, start=1)
                ],
            )
        )

    return CandidateResponse(
        session_id=session_id,
        total_candidatos=total_candidatos,
        pairs=pair_schemas,
    )
