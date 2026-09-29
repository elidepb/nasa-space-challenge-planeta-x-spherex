"""Consulta NASA/IPAC IRSA y descarga cutouts FITS de SPHEREx."""

from __future__ import annotations

import hashlib
import io
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from astropy.table import Table

from spherex_pipeline.constants import (
    CACHE_DIR,
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DOWNLOAD_RETRIES,
    IRSA_BASE_URL,
    IRSA_SIA_URL,
    IRSA_TAP_SYNC_URL,
    IRSA_TAP_URL,
    KNOWN_BANDPASSES,
    KNOWN_RELEASES,
    REMOTE_TIMEOUT_S,
)

LOGGER = logging.getLogger(__name__)

_QR_ALIASES = {
    "2": "qr2",
    "3": "qr3",
    "qr2": "qr2",
    "qr3": "qr3",
    "qr-2": "qr2",
    "qr-3": "qr3",
    "qr2_deep": "qr2_deep",
    "qr3_deep": "qr3_deep",
    "qr2-deep": "qr2_deep",
    "qr3-deep": "qr3_deep",
    "qr2deep": "qr2_deep",
    "qr3deep": "qr3_deep",
}


def normalize_qr(qr: str) -> str:
    """Normaliza QR2/QR3/... al identificador canónico usado en IRSA."""
    raw = str(qr).strip().lower().replace(" ", "")
    raw = raw.removeprefix("spherex_").removeprefix("spherex")
    key = _QR_ALIASES.get(raw)
    if key not in KNOWN_RELEASES:
        raise ValueError(
            f"QR no reconocido: {qr!r}. Valores válidos: {tuple(KNOWN_RELEASES)}"
        )
    return key


@dataclass
class IrsaRecord:
    access_url: str
    cutout_url: str
    time_mjd: float | None
    bandpass: str | None
    obs_id: str | None = None


def resolve_bandpass(bandpass: str | None = None, detector: int | str | None = None) -> str:
    """Exige una sola banda/detector para comparar épocas en la misma λ."""
    derived = None
    if detector is not None and str(detector).strip() != "":
        try:
            det = int(detector)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"detector no válido: {detector!r}") from exc
        if det not in range(1, 7):
            raise ValueError("detector debe estar entre 1 y 6.")
        derived = f"SPHEREx-D{det}"

    chosen = (bandpass or "").strip() or None
    if chosen and derived and chosen != derived:
        raise ValueError(
            f"bandpass {chosen!r} no coincide con detector {detector!r} ({derived})."
        )
    chosen = chosen or derived
    if not chosen:
        raise ValueError(
            "Indique bandpass (SPHEREx-D1 ... SPHEREx-D6) o detector (1 ... 6) "
            "para mantener comparaciones espectralmente equivalentes."
        )
    if chosen not in KNOWN_BANDPASSES:
        raise ValueError(
            f"bandpass no reconocido: {chosen!r}. Valores válidos: {KNOWN_BANDPASSES}"
        )
    return chosen


def extract_qr_from_url(url: str) -> str | None:
    matches = [
        key for key, meta in KNOWN_RELEASES.items() if meta["uri_fragment"] in url
    ]
    if not matches:
        return None
    return max(matches, key=len)


def dedupe_records(records: list[IrsaRecord]) -> tuple[list[IrsaRecord], int]:
    seen: set[str] = set()
    unique: list[IrsaRecord] = []
    duplicates = 0
    for record in records:
        key = record.access_url.split("?")[0]
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(record)
    return unique, duplicates


def cutout_url(access_url: str, ra: float, dec: float, size_deg: float) -> str:
    base = access_url.split("?")[0]
    return f"{base}?center={ra},{dec}&size={size_deg}"


def _tap_adql(ra: float, dec: float, bandpass: str, qr: str) -> str:
    uri_fragment = KNOWN_RELEASES[qr]["uri_fragment"]
    return f"""
SELECT
    '{IRSA_BASE_URL}' || a.uri AS access_url,
    p.time_bounds_lower,
    p.energy_bandpassname
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly)
      AND p.energy_bandpassname = '{bandpass}'
      AND a.uri LIKE '%{uri_fragment}%'
ORDER BY p.time_bounds_lower
""".strip()


def _query_tap_pyvo(adql: str) -> Table:
    import pyvo

    service = pyvo.dal.TAPService(IRSA_TAP_URL)
    return service.search(adql).to_table()


def _query_tap_http(adql: str) -> Table:
    payload = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "votable",
            "QUERY": adql,
        }
    ).encode("utf-8")
    request = urllib.request.Request(IRSA_TAP_SYNC_URL, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT_S) as response:
        raw = response.read()
    return Table.read(io.BytesIO(raw), format="votable")


def query_tap(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
) -> list[IrsaRecord]:
    """Busca todas las épocas SPHEREx de un QR + banda que cubren (ra, dec)."""
    qr = normalize_qr(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    adql = _tap_adql(ra, dec, bandpass, qr)
    errors: list[str] = []
    table = None
    for method, fn in (("pyvo", _query_tap_pyvo), ("http", _query_tap_http)):
        try:
            table = fn(adql)
            LOGGER.info("Consulta TAP IRSA (%s, %s, %s): %s filas", method, qr, bandpass, len(table))
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{method}: {exc}")
            LOGGER.warning("TAP IRSA falló (%s): %s", method, exc)
    if table is None:
        raise RuntimeError("No se pudo consultar TAP de IRSA. " + " | ".join(errors))

    records: list[IrsaRecord] = []
    for row in table:
        access = str(row["access_url"])
        time_mjd = _optional_float(row, "time_bounds_lower")
        band = str(row["energy_bandpassname"]) if "energy_bandpassname" in table.colnames else bandpass
        records.append(
            IrsaRecord(
                access_url=access,
                cutout_url=cutout_url(access, ra, dec, size_deg),
                time_mjd=time_mjd,
                bandpass=band,
            )
        )
    return records


def query_sia(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
) -> list[IrsaRecord]:
    """Respaldo: Simple Image Access v2 de IRSA, acotado al QR pedido."""
    qr = normalize_qr(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    collection = KNOWN_RELEASES[qr]["sia_collection"]
    radius = max(size_deg / 2.0, 1.0 / 3600.0)
    params = urllib.parse.urlencode(
        {
            "COLLECTION": collection,
            "POS": f"circle {ra} {dec} {radius}",
            "RESPONSEFORMAT": "votable",
        }
    )
    url = f"{IRSA_SIA_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=REMOTE_TIMEOUT_S) as response:
            table = Table.read(io.BytesIO(response.read()), format="votable")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"No se pudo consultar SIA de IRSA ({collection}): {exc}") from exc

    records: list[IrsaRecord] = []
    for row in table:
        row_band = None
        if "energy_bandpassname" in table.colnames:
            row_band = str(row["energy_bandpassname"])
        if row_band and row_band != bandpass:
            continue
        access = str(row["access_url"])
        time_mjd = _optional_float(row, "t_min")
        obs_id = str(row["obs_id"]) if "obs_id" in table.colnames else None
        records.append(
            IrsaRecord(
                access_url=access,
                cutout_url=cutout_url(access, ra, dec, size_deg),
                time_mjd=time_mjd,
                bandpass=row_band or bandpass,
                obs_id=obs_id,
            )
        )
    records.sort(key=lambda item: item.time_mjd if item.time_mjd is not None else 0.0)
    LOGGER.info("Consulta SIA IRSA (%s, %s): %s filas", qr, bandpass, len(records))
    return records


def query_observations(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
) -> list[IrsaRecord]:
    """TAP primero; si falla o no hay filas, SIA del mismo QR."""
    qr = normalize_qr(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    try:
        records = query_tap(ra, dec, size_deg, qr=qr, bandpass=bandpass)
        if records:
            return records
        LOGGER.warning("TAP no devolvió imágenes para %s %s; se intenta SIA.", qr, bandpass)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("TAP no disponible (%s); se intenta SIA.", exc)
    return query_sia(ra, dec, size_deg, qr=qr, bandpass=bandpass)


def subsample_epochs(records: list[IrsaRecord], max_observations: int | None) -> list[IrsaRecord]:
    if max_observations is None or max_observations <= 0 or len(records) <= max_observations:
        return records
    import numpy as np

    indices = np.unique(np.linspace(0, len(records) - 1, max_observations).round().astype(int))
    return [records[int(index)] for index in indices]


def download_cutout(url: str, cache_dir: Path | None = None) -> Path:
    """Descarga un cutout FITS a caché local, con reintentos."""
    cache_dir = Path(cache_dir or CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    dest = cache_dir / f"cutout_{digest}.fits"
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    last_error: Exception | None = None
    for attempt in range(DOWNLOAD_RETRIES):
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT_S) as response:
                dest.write_bytes(response.read())
            if dest.stat().st_size == 0:
                raise RuntimeError(f"Cutout vacío: {url}")
            return dest
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, Exception) as exc:
            last_error = exc
            wait = 10 * (attempt + 1)
            LOGGER.warning("Descarga fallida (%s/%s): %s. Reintento en %ss", attempt + 1, DOWNLOAD_RETRIES, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"No se pudo descargar el cutout {url}") from last_error


def _optional_float(row, column: str) -> float | None:
    try:
        value = row[column]
    except Exception:  # noqa: BLE001
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number
