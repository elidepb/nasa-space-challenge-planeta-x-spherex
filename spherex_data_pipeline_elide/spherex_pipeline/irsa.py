"""Consulta NASA/IPAC IRSA y descarga cutouts FITS de SPHEREx."""

from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from astropy.table import Table
from astropy.time import Time

from spherex_pipeline.constants import (
    CACHE_DIR,
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DOWNLOAD_RETRIES,
    IBE_SPHEREX_DATA_MARKER,
    IRSA_BASE_URL,
    IRSA_SIA_URL,
    IRSA_TAP_SYNC_URL,
    IRSA_TAP_URL,
    KNOWN_BANDPASSES,
    KNOWN_RELEASES,
    REMOTE_TIMEOUT_S,
    SPHEREX_S3_HTTPS_BASE,
)

LOGGER = logging.getLogger(__name__)

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMERIC = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")

_QR_ALIASES = {
    "1": "dr1",
    "2": "qr2",
    "3": "qr3",
    "dr1": "dr1",
    "dr-1": "dr1",
    "qr2": "qr2",
    "qr3": "qr3",
    "qr-2": "qr2",
    "qr-3": "qr3",
    "dr1_deep": "dr1_deep",
    "qr2_deep": "qr2_deep",
    "qr3_deep": "qr3_deep",
    "dr1-deep": "dr1_deep",
    "qr2-deep": "qr2_deep",
    "qr3-deep": "qr3_deep",
    "dr1deep": "dr1_deep",
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


def searchable_release(qr: str) -> str:
    """QR2 ya no está en TAP/SIA; IRSA pide DR1 (surveys 1–2) y QR3 (3–4)."""
    qr = normalize_qr(qr)
    meta = KNOWN_RELEASES[qr]
    if meta.get("searchable", True):
        return qr
    successor = str(meta.get("superseded_by") or DEFAULT_QR)
    LOGGER.warning(
        "IRSA ya no indexa %s en TAP/SIA (QR2 dejó de ser buscable). Se consulta %s.",
        qr,
        successor,
    )
    return successor


@dataclass
class IrsaRecord:
    access_url: str
    cutout_url: str
    time_mjd: float | None
    bandpass: str | None
    obs_id: str | None = None


@dataclass
class DownloadResult:
    path: Path
    url: str
    kind: str  # "cutout" | "mef"


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


def full_mef_url(access_url: str) -> str:
    """Quita el query string del access URL: el MEF completo, no el recorte."""
    return access_url.split("?")[0]


def s3_mef_url(access_url: str) -> str | None:
    """Mirror público AWS del mismo MEF on-prem. None si la URI no es IBE SPHEREx."""
    base = full_mef_url(access_url)
    marker = IBE_SPHEREX_DATA_MARKER
    index = base.find(marker)
    if index < 0:
        return None
    key = base[index + len(marker) :].lstrip("/")
    if not key:
        return None
    return f"{SPHEREX_S3_HTTPS_BASE}/{key}"


def parse_time_bound(value: Any, *, end_of_day: bool = False) -> float | None:
    """Convierte ISO, fecha o MJD a MJD. ``None`` o vacío no filtran."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return float(Time(value, scale="utc").mjd)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if _NUMERIC.fullmatch(text):
        return float(text)
    if _DATE_ONLY.fullmatch(text):
        text = f"{text}T23:59:59.999" if end_of_day else f"{text}T00:00:00"
    try:
        return float(Time(text.replace("Z", ""), format="isot", scale="utc").mjd)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"timestamp no válido: {value!r}. Use ISO-8601 (2025-05-01 o 2025-05-01T12:00:00) o MJD."
        ) from exc


def normalize_time_range(
    time_start: Any = None, time_end: Any = None
) -> tuple[float | None, float | None]:
    """Devuelve (MJD mínimo, MJD máximo) inclusivos. Sin valores, no hay filtro."""
    tmin = parse_time_bound(time_start, end_of_day=False)
    tmax = parse_time_bound(time_end, end_of_day=True)
    if tmin is not None and tmax is not None and tmin > tmax:
        raise ValueError("time_start no puede ser posterior a time_end.")
    return tmin, tmax


def filter_records_by_time(
    records: list[IrsaRecord],
    time_min_mjd: float | None,
    time_max_mjd: float | None,
) -> list[IrsaRecord]:
    if time_min_mjd is None and time_max_mjd is None:
        return records
    kept: list[IrsaRecord] = []
    for record in records:
        t = record.time_mjd
        if t is None:
            continue
        if time_min_mjd is not None and t < time_min_mjd:
            continue
        if time_max_mjd is not None and t > time_max_mjd:
            continue
        kept.append(record)
    return kept


def _tap_adql(
    ra: float,
    dec: float,
    bandpass: str,
    qr: str,
    time_min_mjd: float | None = None,
    time_max_mjd: float | None = None,
) -> str:
    uri_fragment = KNOWN_RELEASES[qr]["uri_fragment"]
    clauses = [
        f"1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly)",
        f"p.energy_bandpassname = '{bandpass}'",
        f"a.uri LIKE '%{uri_fragment}%'",
    ]
    if time_min_mjd is not None:
        clauses.append(f"p.time_bounds_lower >= {time_min_mjd:.8f}")
    if time_max_mjd is not None:
        clauses.append(f"p.time_bounds_lower <= {time_max_mjd:.8f}")
    where = "\n      AND ".join(clauses)
    return f"""
SELECT
    '{IRSA_BASE_URL}' || a.uri AS access_url,
    p.time_bounds_lower,
    p.energy_bandpassname
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE {where}
ORDER BY p.time_bounds_lower
""".strip()


# El proxy de Apache delante de /TAP/sync corta la conexión si el ADQL
# (CONTAINS sobre el polígono SPHEREx) tarda demasiado, y responde 502 Proxy Error.
# Un 502 que vuelve enseguida suele ser un fallo breve; uno tardío ya agotó ese proxy.
_TAP_SYNC_BLIP_S = 15
_TAP_SYNC_RETRY_WAIT_S = 2
# El proxy de IRSA alterna 502 y 200 durante minutos: SIA se reintenta con espera creciente
# (3+6+9+12+15 s como máximo por colección) antes de rendirse.
_SIA_ATTEMPTS = 6
_SIA_RETRY_WAIT_S = 3
_TAP_ASYNC_TIMEOUT_S = 600


def _exception_http_status(exc: BaseException) -> int | None:
    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code)
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code > 0:
        return code
    cause = getattr(exc, "cause", None)
    if isinstance(cause, BaseException) and cause is not exc:
        return _exception_http_status(cause)
    return None


def _is_gateway_error(exc: BaseException) -> bool:
    """502/503/504 del proxy de IRSA, no un error de ADQL."""
    if _exception_http_status(exc) in _UNAVAILABLE_HTTP:
        return True
    text = str(exc)
    return any(
        marker in text
        for marker in ("Proxy Error", "Bad Gateway", "Gateway Timeout", "Gateway Time-out")
    )


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if "Timeout" in type(exc).__name__:
        return True
    cause = getattr(exc, "cause", None)
    if isinstance(cause, BaseException) and cause is not exc and _is_timeout_error(cause):
        return True
    return "timed out" in str(exc).lower()


def _is_tap_sync_failure(exc: BaseException) -> bool:
    """El sync no contestó: proxy 502/503/504 o la conexión se quedó colgada."""
    return _is_gateway_error(exc) or _is_timeout_error(exc)


def _pyvo_tap_service():
    import pyvo
    import requests

    class _TimeoutSession(requests.Session):
        def request(self, *args, **kwargs):
            kwargs.setdefault("timeout", REMOTE_TIMEOUT_S)
            return super().request(*args, **kwargs)

    return pyvo.dal.TAPService(IRSA_TAP_URL, session=_TimeoutSession())


def _pyvo_run_async(service, adql: str) -> Table:
    import inspect

    kwargs = {}
    if "timeout" in inspect.signature(service.run_async).parameters:
        kwargs["timeout"] = _TAP_ASYNC_TIMEOUT_S
    return service.run_async(adql, **kwargs).to_table()


def _query_tap_pyvo(adql: str) -> tuple[Table, str]:
    """Sync primero. Si el proxy de /TAP/sync responde 502/503/504, el mismo ADQL va en async."""
    service = _pyvo_tap_service()
    started = time.monotonic()
    try:
        return service.search(adql).to_table(), "pyvo"
    except Exception as exc:
        if not _is_tap_sync_failure(exc):
            raise
        if time.monotonic() - started < _TAP_SYNC_BLIP_S:
            LOGGER.warning(
                "TAP sync IRSA respondió %s; se reintenta una vez (el proxy a veces falla un instante).",
                exc,
            )
            time.sleep(_TAP_SYNC_RETRY_WAIT_S)
            try:
                return service.search(adql).to_table(), "pyvo"
            except Exception as retry_exc:
                if not _is_tap_sync_failure(retry_exc):
                    raise
                exc = retry_exc
        LOGGER.warning(
            "TAP sync IRSA sigue en %s. /TAP/sync lo corta el proxy; se envía la misma consulta en asíncrono.",
            exc,
        )
        return _pyvo_run_async(service, adql), "pyvo-async"


def _read_votable(raw: bytes) -> Table:
    """Los FIELD de IRSA traen ID=col_N; sin esto Astropy oculta access_url."""
    return Table.read(io.BytesIO(raw), format="votable", use_names_over_ids=True)


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
        return _read_votable(response.read())


def query_tap(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
    time_start: Any = None,
    time_end: Any = None,
) -> list[IrsaRecord]:
    """Busca épocas SPHEREx de un QR + banda que cubren (ra, dec), opcionalmente en un intervalo."""
    qr = searchable_release(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    time_min_mjd, time_max_mjd = normalize_time_range(time_start, time_end)
    adql = _tap_adql(
        ra,
        dec,
        bandpass,
        qr,
        time_min_mjd=time_min_mjd,
        time_max_mjd=time_max_mjd,
    )
    errors: list[str] = []
    table = None
    method = ""
    try:
        table, method = _query_tap_pyvo(adql)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pyvo: {exc}")
        LOGGER.warning("TAP IRSA falló (pyvo): %s", exc)
        # Otro POST a /TAP/sync repite el mismo corte del proxy. Solo sirve si pyvo
        # falló por otra causa (no está instalado, error de protocolo, etc.).
        if not _is_tap_sync_failure(exc):
            try:
                table = _query_tap_http(adql)
                method = "http"
            except Exception as http_exc:  # noqa: BLE001
                errors.append(f"http: {http_exc}")
                LOGGER.warning("TAP IRSA falló (http): %s", http_exc)
    if table is None:
        raise RuntimeError("No se pudo consultar TAP de IRSA. " + " | ".join(errors))
    LOGGER.info(
        "Consulta TAP IRSA (%s, %s, %s, time=%s..%s): %s filas",
        method,
        qr,
        bandpass,
        time_start,
        time_end,
        len(table),
    )

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
    return filter_records_by_time(records, time_min_mjd, time_max_mjd)


def query_sia(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
    time_start: Any = None,
    time_end: Any = None,
) -> list[IrsaRecord]:
    """Respaldo: Simple Image Access v2 de IRSA, acotado al QR pedido."""
    qr = searchable_release(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    time_min_mjd, time_max_mjd = normalize_time_range(time_start, time_end)
    radius = max(size_deg / 2.0, 1.0 / 3600.0)
    preferred = KNOWN_RELEASES[qr]["sia_collection"]
    collections = [preferred]
    for extra in ("spherex_dr1", "spherex_qr3"):
        if extra not in collections:
            collections.append(extra)

    table = None
    collection = preferred
    errors: list[str] = []
    for collection in collections:
        params: dict[str, str] = {
            "COLLECTION": collection,
            "POS": f"circle {ra} {dec} {radius}",
            "RESPONSEFORMAT": "votable",
        }
        if time_min_mjd is not None or time_max_mjd is not None:
            lo = "-Inf" if time_min_mjd is None else f"{time_min_mjd:.8f}"
            hi = "+Inf" if time_max_mjd is None else f"{time_max_mjd:.8f}"
            params["TIME"] = f"{lo} {hi}"
        url = f"{IRSA_SIA_URL}?{urllib.parse.urlencode(params)}"
        last_exc: Exception | None = None
        for attempt in range(1, _SIA_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(url, timeout=REMOTE_TIMEOUT_S) as response:
                    table = _read_votable(response.read())
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < _SIA_ATTEMPTS and _is_tap_sync_failure(exc):
                    wait = _SIA_RETRY_WAIT_S * attempt
                    LOGGER.warning(
                        "SIA IRSA %s intento %s/%s: %s. Se reintenta en %ss.",
                        collection,
                        attempt,
                        _SIA_ATTEMPTS,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                break
        if table is not None:
            break
        errors.append(f"{collection}: {last_exc}")
        LOGGER.warning("SIA IRSA falló (%s): %s", collection, last_exc)
    if table is None:
        raise RuntimeError("No se pudo consultar SIA de IRSA. " + " | ".join(errors))

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
    records = filter_records_by_time(records, time_min_mjd, time_max_mjd)
    LOGGER.info(
        "Consulta SIA IRSA (%s, %s, %s, time=%s..%s): %s filas",
        collection,
        qr,
        bandpass,
        time_start,
        time_end,
        len(records),
    )
    return records


def query_observations(
    ra: float,
    dec: float,
    size_deg: float,
    *,
    qr: str = DEFAULT_QR,
    bandpass: str = DEFAULT_BANDPASS,
    detector: int | str | None = None,
    time_start: Any = None,
    time_end: Any = None,
) -> list[IrsaRecord]:
    """SIA primero (DR1/QR3). TAP a menudo 502 tras el retiro de QR2 del índice.

    Los resultados no vacíos se guardan unos minutos en memoria: la API consulta el
    catálogo al responder y otra vez al descargar, y repetirlo duplica la exposición
    a los 502 intermitentes de IRSA.
    """
    qr = searchable_release(qr)
    bandpass = resolve_bandpass(bandpass, detector)
    cache_key = (round(float(ra), 6), round(float(dec), 6), float(size_deg), qr, bandpass, str(time_start), str(time_end))
    cached = _catalog_cache_get(cache_key)
    if cached is not None:
        LOGGER.info("Catálogo IRSA servido desde caché en memoria (%s filas).", len(cached))
        return cached
    records = _query_observations_remote(ra, dec, size_deg, qr, bandpass, time_start, time_end)
    if records:
        _catalog_cache_put(cache_key, records)
    return records


_CATALOG_CACHE_TTL_S = 600.0
_CATALOG_CACHE: dict[tuple, tuple[float, list[IrsaRecord]]] = {}
_CATALOG_CACHE_LOCK = threading.Lock()


def _catalog_cache_get(key: tuple) -> list[IrsaRecord] | None:
    with _CATALOG_CACHE_LOCK:
        entry = _CATALOG_CACHE.get(key)
        if entry is None:
            return None
        stored_at, records = entry
        if time.monotonic() - stored_at > _CATALOG_CACHE_TTL_S:
            del _CATALOG_CACHE[key]
            return None
        return list(records)


def _catalog_cache_put(key: tuple, records: list[IrsaRecord]) -> None:
    with _CATALOG_CACHE_LOCK:
        _CATALOG_CACHE[key] = (time.monotonic(), list(records))


def _query_observations_remote(
    ra: float,
    dec: float,
    size_deg: float,
    qr: str,
    bandpass: str,
    time_start: Any,
    time_end: Any,
) -> list[IrsaRecord]:
    try:
        records = query_sia(
            ra,
            dec,
            size_deg,
            qr=qr,
            bandpass=bandpass,
            time_start=time_start,
            time_end=time_end,
        )
        if records:
            return records
        LOGGER.warning("SIA no devolvió imágenes para %s %s; se intenta TAP.", qr, bandpass)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("SIA no disponible (%s); se intenta TAP.", exc)
    return query_tap(
        ra,
        dec,
        size_deg,
        qr=qr,
        bandpass=bandpass,
        time_start=time_start,
        time_end=time_end,
    )


def subsample_epochs(records: list[IrsaRecord], max_observations: int | None) -> list[IrsaRecord]:
    if max_observations is None or max_observations <= 0 or len(records) <= max_observations:
        return records
    import numpy as np

    indices = np.unique(np.linspace(0, len(records) - 1, max_observations).round().astype(int))
    return [records[int(index)] for index in indices]


_UNAVAILABLE_HTTP = {502, 503, 504}
_CHUNK_BYTES = 1024 * 1024


def _http_status(exc: BaseException) -> int | None:
    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code)
    return None


def _is_unavailable(exc: BaseException) -> bool:
    return _http_status(exc) in _UNAVAILABLE_HTTP


def _cache_path(url: str, cache_dir: Path, prefix: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{prefix}_{digest}.fits"


def _download_to_path(
    url: str,
    dest: Path,
    *,
    retry_unavailable: bool = True,
) -> Path:
    """Descarga ``url`` a ``dest`` en streaming. Si ya existe y no está vacío, no toca red."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    last_error: Exception | None = None
    tmp = dest.with_name(f".{dest.name}.part")
    for attempt in range(DOWNLOAD_RETRIES):
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT_S) as response:
                with tmp.open("wb") as handle:
                    while True:
                        chunk = response.read(_CHUNK_BYTES)
                        if not chunk:
                            break
                        handle.write(chunk)
            if tmp.stat().st_size == 0:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"Archivo vacío: {url}")
            tmp.replace(dest)
            return dest
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as exc:
            last_error = exc
            tmp.unlink(missing_ok=True)
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)
            if (not retry_unavailable) and _is_unavailable(exc):
                raise
            if attempt + 1 >= DOWNLOAD_RETRIES:
                break
            wait = 10 * (attempt + 1)
            LOGGER.warning(
                "Descarga fallida (%s/%s): %s. Reintento en %ss",
                attempt + 1,
                DOWNLOAD_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"No se pudo descargar {url}") from last_error


def download_cutout(url: str, cache_dir: Path | None = None) -> Path:
    """Descarga un cutout FITS a caché. Ante 502/503/504 no reintenta (el backend SPHEREx no vuelve)."""
    cache_dir = Path(cache_dir or CACHE_DIR)
    dest = _cache_path(url, cache_dir, "cutout")
    return _download_to_path(url, dest, retry_unavailable=False)


def download_record(record: IrsaRecord, cache_dir: Path | None = None) -> DownloadResult:
    """Cutout IBE primero; si ese servicio no responde, MEF completo (S3, luego IBE)."""
    cache_dir = Path(cache_dir or CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cutout_dest = _cache_path(record.cutout_url, cache_dir, "cutout")
    cutout_error: Exception | None = None
    try:
        path = _download_to_path(record.cutout_url, cutout_dest, retry_unavailable=False)
        LOGGER.info("Cutout IBE: %s", record.cutout_url.split("/")[-1])
        return DownloadResult(path=path, url=record.cutout_url, kind="cutout")
    except Exception as exc:  # noqa: BLE001
        cutout_error = exc
        if _is_unavailable(exc):
            LOGGER.warning(
                "Cutout IBE no disponible (%s); se descarga el MEF completo.",
                _http_status(exc) or exc,
            )
        else:
            LOGGER.warning("Cutout IBE falló (%s); se intenta el MEF completo.", exc)

    mef_access = full_mef_url(record.access_url)
    candidates: list[tuple[str, str]] = []
    s3_url = s3_mef_url(record.access_url)
    if s3_url:
        candidates.append((s3_url, "s3"))
    if mef_access and mef_access != s3_url:
        candidates.append((mef_access, "ibe"))

    errors: list[str] = []
    for url, host in candidates:
        dest = _cache_path(url, cache_dir, "mef")
        try:
            path = _download_to_path(url, dest, retry_unavailable=True)
            LOGGER.info("MEF %s (%s): %s", host, path.stat().st_size, url.split("/")[-1])
            return DownloadResult(path=path, url=url, kind="mef")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}: {exc}")
            LOGGER.warning("MEF %s falló: %s", host, exc)

    detail = " | ".join(errors) if errors else str(cutout_error)
    raise RuntimeError(
        f"No se pudo obtener {mef_access.split('/')[-1]} "
        f"(cutout IBE y MEF). {detail}"
    ) from cutout_error


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
