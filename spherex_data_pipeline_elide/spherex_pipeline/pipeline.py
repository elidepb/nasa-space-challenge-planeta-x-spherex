"""Orquestación del pipeline: consulta, descarga, lectura, máscara y contrato."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from astropy.utils.data import conf as astropy_data_conf

from spherex_pipeline.constants import (
    CACHE_DIR,
    DEFAULT_BANDPASS,
    DEFAULT_MAX_WORKERS,
    DEFAULT_QR,
    DEFAULT_SOURCE,
    REMOTE_TIMEOUT_S,
)
from spherex_pipeline.cutouts import cutout_region, homogenize_shapes
from spherex_pipeline.demo import load_demo_observations
from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.irsa import (
    IrsaRecord,
    dedupe_records,
    download_cutout,
    normalize_qr,
    query_observations,
    resolve_bandpass,
    subsample_epochs,
)
from spherex_pipeline.masking import apply_invalid_mask
from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)
astropy_data_conf.remote_timeout = REMOTE_TIMEOUT_S


@dataclass
class FailureRecord:
    id: str
    url: str
    stage: str
    error_type: str
    message: str

    def line(self) -> str:
        return f"{self.id} | {self.stage} | {self.error_type} | {self.message} | {self.url}"


@dataclass
class RetrievalReport:
    tap_matches: int = 0
    requested: int = 0
    downloaded: int = 0
    parsed: int = 0
    observations: int = 0
    failed_downloads: int = 0
    failed_parses: int = 0
    duplicates: int = 0
    failures: list[FailureRecord] = field(default_factory=list)


@dataclass
class PipelineResult:
    observations: list[Observation]
    report: RetrievalReport
    query: dict[str, object]


def _apply_mask(observation: Observation) -> Observation:
    if observation.flags is None:
        observation.valid_mask = None if observation.image is None else np.isfinite(observation.image)
        return observation
    masked, valid = apply_invalid_mask(
        observation.image,
        observation.flags,
        variance=observation.variance,
    )
    observation.image = masked
    observation.valid_mask = valid
    observation.metadata["n_invalid_pixels"] = int(valid.size - valid.sum())
    observation.metadata["n_valid_pixels"] = int(valid.sum())
    return observation


def _prepare(observations: list[Observation], ra: float, dec: float, size: float) -> list[Observation]:
    prepared: list[Observation] = []
    for observation in observations:
        observation = cutout_region(observation, ra, dec, size)
        observation = _apply_mask(observation)
        prepared.append(observation)
    prepared = homogenize_shapes(prepared)
    prepared.sort(key=lambda item: item.timestamp)
    return prepared


def _from_irsa(
    ra: float,
    dec: float,
    size: float,
    qr: str,
    bandpass: str,
    max_observations: int | None,
    cache_dir: Path,
    max_workers: int,
) -> tuple[list[Observation], RetrievalReport]:
    raw_records = query_observations(ra, dec, size, qr=qr, bandpass=bandpass)
    unique_records, n_dupes = dedupe_records(raw_records)
    records = subsample_epochs(unique_records, max_observations)
    report = RetrievalReport(
        tap_matches=len(unique_records),
        requested=len(records),
        duplicates=n_dupes,
    )
    if not records:
        return [], report

    observations: list[Observation] = []

    def _one(record: IrsaRecord):
        url = record.cutout_url
        try:
            local = download_cutout(url, cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001
            return ("download", record, None, exc)
        try:
            obs = observation_from_fits(
                local,
                observation_id=record.obs_id,
                ra=ra,
                dec=dec,
                timestamp_mjd=record.time_mjd,
                extra_metadata={
                    "qr": qr,
                    "bandpass": record.bandpass or bandpass,
                    "source": "irsa",
                    "access_url": record.access_url,
                    "cutout_url": record.cutout_url,
                    "local_path": str(local),
                },
            )
            obs.fits_source = record.access_url
            return ("ok", record, obs, None)
        except Exception as exc:  # noqa: BLE001
            return ("parse", record, None, exc)

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = [pool.submit(_one, record) for record in records]
        for future in as_completed(futures):
            stage, record, obs, exc = future.result()
            ident = record.obs_id or record.access_url.split("/")[-1]
            if stage == "ok":
                observations.append(obs)
                report.downloaded += 1
                report.parsed += 1
            elif stage == "download":
                report.failed_downloads += 1
                report.failures.append(
                    FailureRecord(
                        id=str(ident),
                        url=record.cutout_url,
                        stage="download",
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
                LOGGER.error("Descarga fallida %s: %s", ident, exc)
            else:
                report.downloaded += 1
                report.failed_parses += 1
                report.failures.append(
                    FailureRecord(
                        id=str(ident),
                        url=record.cutout_url,
                        stage="parse",
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
                LOGGER.error("Parse fallido %s: %s", ident, exc)

    report.observations = len(observations)
    return observations, report


def run_pipeline(
    ra: float,
    dec: float,
    size: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
    source: str = DEFAULT_SOURCE,
    max_observations: int | None = None,
    cache_dir: str | Path | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    demo_dir: str | Path | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline y devuelve observaciones + informe de recuperación."""
    global LAST_RESULT
    source = source.lower().strip()
    if source not in {"demo", "irsa"}:
        raise ValueError("source debe ser 'irsa' o 'demo'")

    qr = normalize_qr(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    query = {
        "ra": ra,
        "dec": dec,
        "size": size,
        "qr": qr,
        "bandpass": bandpass,
        "source": source,
        "max_observations": max_observations,
    }
    LOGGER.info("run_pipeline %s", query)

    if source == "demo":
        observations = load_demo_observations(demo_dir)
        prepared = _prepare(observations, ra, dec, size)
        for observation in prepared:
            observation.metadata["qr"] = qr
            observation.metadata["bandpass"] = bandpass
            observation.metadata.setdefault("source", "demo")
        report = RetrievalReport(
            tap_matches=len(prepared),
            requested=len(prepared),
            downloaded=len(prepared),
            parsed=len(prepared),
            observations=len(prepared),
        )
        result = PipelineResult(observations=prepared, report=report, query=query)
        LAST_RESULT = result
        return result

    observations, report = _from_irsa(
        ra,
        dec,
        size,
        qr=qr,
        bandpass=bandpass,
        max_observations=max_observations,
        cache_dir=Path(cache_dir or CACHE_DIR),
        max_workers=max_workers,
    )
    prepared = _prepare(observations, ra, dec, size)
    report.observations = len(prepared)
    result = PipelineResult(observations=prepared, report=report, query=query)
    LAST_RESULT = result
    return result


LAST_RESULT: PipelineResult | None = None


def get_observations(
    ra: float,
    dec: float,
    size: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
    source: str = DEFAULT_SOURCE,
    max_observations: int | None = None,
    cache_dir: str | Path | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    demo_dir: str | Path | None = None,
) -> list[Observation]:
    """Devuelve todas las épocas SPHEREx de una región, ordenadas en el tiempo.

    Si TAP no encuentra productos, devuelve una lista vacía.
    Los fallos de descarga/parseo se registran en ``LAST_RESULT.report`` y
    se relanzan para que el consumidor no reciba un conjunto incompleto.
    """
    result = run_pipeline(
        ra,
        dec,
        size,
        qr=qr,
        bandpass=bandpass,
        detector=detector,
        source=source,
        max_observations=max_observations,
        cache_dir=cache_dir,
        max_workers=max_workers,
        demo_dir=demo_dir,
    )
    if result.report.failures:
        details = " | ".join(item.line() for item in result.report.failures[:5])
        raise RuntimeError(
            f"{len(result.report.failures)} observaciones fallaron "
            f"(download={result.report.failed_downloads}, parse={result.report.failed_parses}). "
            + details
        )
    return result.observations
