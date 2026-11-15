"""Tests unitarios del cliente IRSA, sin red."""

import io
from email.message import EmailMessage
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from astropy.table import Table

from spherex_pipeline.irsa import (
    IrsaRecord,
    _is_gateway_error,
    _tap_adql,
    searchable_release,
    cutout_url,
    download_record,
    filter_records_by_time,
    full_mef_url,
    normalize_qr,
    normalize_time_range,
    parse_time_bound,
    query_tap,
    resolve_bandpass,
    s3_mef_url,
    subsample_epochs,
)


ACCESS = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W19_2B/l2b-v20-2025-247/2/file.fits"


def test_cutout_url_appends_center_and_size():
    url = cutout_url(ACCESS, 210.8, 54.3, 0.05)
    assert url.endswith("file.fits?center=210.8,54.3&size=0.05")


def test_s3_mef_url_maps_ibe_path():
    assert s3_mef_url(ACCESS) == (
        "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"
        "qr2/level2/2025W19_2B/l2b-v20-2025-247/2/file.fits"
    )
    assert s3_mef_url(ACCESS + "?center=1,2&size=0.05") == s3_mef_url(ACCESS)
    assert full_mef_url(ACCESS + "?center=1,2&size=0.05") == ACCESS
    assert s3_mef_url("https://example.com/other.fits") is None


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._buf.read() if n < 0 else self._buf.read(n)


def _http_error(url: str, code: int) -> HTTPError:
    return HTTPError(url, code, "Service Temporarily Unavailable", EmailMessage(), io.BytesIO(b"<html>503</html>"))


def test_download_record_falls_back_to_s3_on_cutout_503(tmp_path):
    record = IrsaRecord(
        access_url=ACCESS,
        cutout_url=ACCESS + "?center=210.8,54.3&size=0.05",
        time_mjd=60810.0,
        bandpass="SPHEREx-D2",
    )
    payload = b"SIMPLE  =                    T" + b" " * 50

    def fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "?center=" in url:
            raise _http_error(url, 503)
        if "nasa-irsa-spherex" in url:
            return _FakeResponse(payload)
        raise AssertionError(f"no se esperaba {url}")

    with patch("spherex_pipeline.irsa.urllib.request.urlopen", side_effect=fake_urlopen):
        result = download_record(record, cache_dir=tmp_path)

    assert result.kind == "mef"
    assert "nasa-irsa-spherex" in result.url
    assert result.path.exists()
    assert result.path.read_bytes() == payload
    assert not any(path.name.startswith("cutout_") for path in tmp_path.iterdir())


def test_download_record_uses_cached_cutout_without_network(tmp_path):
    record = IrsaRecord(
        access_url=ACCESS,
        cutout_url=ACCESS + "?center=210.8,54.3&size=0.05",
        time_mjd=60810.0,
        bandpass="SPHEREx-D2",
    )
    first_payload = b"FITS-CUTOUT"
    second_payload = b"SHOULD-NOT-WRITE"

    def first_urlopen(request, timeout=None):
        return _FakeResponse(first_payload)

    with patch("spherex_pipeline.irsa.urllib.request.urlopen", side_effect=first_urlopen):
        first = download_record(record, cache_dir=tmp_path)
    assert first.kind == "cutout"

    def fail_if_called(request, timeout=None):
        raise AssertionError("la caché del cutout no debe tocar la red")

    with patch("spherex_pipeline.irsa.urllib.request.urlopen", side_effect=fail_if_called):
        second = download_record(record, cache_dir=tmp_path)
    assert second.path == first.path
    assert second.path.read_bytes() == first_payload
    assert second_payload not in second.path.read_bytes()


def test_download_record_fails_if_cutout_and_mef_fail(tmp_path):
    record = IrsaRecord(
        access_url=ACCESS,
        cutout_url=ACCESS + "?center=210.8,54.3&size=0.05",
        time_mjd=60810.0,
        bandpass="SPHEREx-D2",
    )

    def always_503(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        raise _http_error(url, 503)

    with (
        patch("spherex_pipeline.irsa.urllib.request.urlopen", side_effect=always_503),
        patch("spherex_pipeline.irsa.time.sleep", return_value=None),
    ):
        with pytest.raises(RuntimeError, match="cutout IBE y MEF"):
            download_record(record, cache_dir=tmp_path)


def test_subsample_epochs_keeps_first_and_last():
    records = [
        IrsaRecord(access_url=str(i), cutout_url=str(i), time_mjd=float(i), bandpass="SPHEREx-D2")
        for i in range(10)
    ]
    sampled = subsample_epochs(records, 4)
    assert len(sampled) == 4
    assert sampled[0].time_mjd == 0.0
    assert sampled[-1].time_mjd == 9.0


def test_subsample_none_returns_all_epochs():
    records = [
        IrsaRecord(access_url=str(i), cutout_url=str(i), time_mjd=float(i), bandpass="SPHEREx-D2")
        for i in range(10)
    ]
    assert subsample_epochs(records, None) is records or len(subsample_epochs(records, None)) == 10
    assert len(subsample_epochs(records, None)) == 10


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("qr2", "qr2"),
        ("QR2", "qr2"),
        ("QR3", "qr3"),
        ("DR1", "dr1"),
        ("spherex_dr1", "dr1"),
        ("spherex_qr2", "qr2"),
        ("qr2_deep", "qr2_deep"),
    ],
)
def test_normalize_qr_aliases(value, expected):
    assert normalize_qr(value) == expected


def test_searchable_release_maps_retired_qr2_to_dr1():
    assert searchable_release("qr2") == "dr1"
    assert searchable_release("DR1") == "dr1"
    assert searchable_release("qr3") == "qr3"


def test_normalize_qr_rejects_unknown():
    with pytest.raises(ValueError, match="QR no reconocido"):
        normalize_qr("qr9")


def test_resolve_bandpass_from_detector():
    assert resolve_bandpass(detector=2) == "SPHEREx-D2"
    assert resolve_bandpass("SPHEREx-D2", detector=2) == "SPHEREx-D2"


def test_parse_time_bound_iso_date_and_mjd():
    start = parse_time_bound("2025-05-01")
    end = parse_time_bound("2025-05-01", end_of_day=True)
    assert start is not None and end is not None
    assert end > start
    assert parse_time_bound(60805.7) == pytest.approx(60805.7)
    with pytest.raises(ValueError, match="timestamp no válido"):
        parse_time_bound("no-es-una-fecha")


def test_normalize_time_range_rejects_inverted_window():
    with pytest.raises(ValueError, match="no puede ser posterior"):
        normalize_time_range("2025-06-01", "2025-05-01")


def test_tap_adql_includes_time_bounds():
    adql = _tap_adql(
        210.80227,
        54.34895,
        "SPHEREx-D2",
        "qr2",
        time_min_mjd=60800.0,
        time_max_mjd=60840.0,
    )
    assert "p.time_bounds_lower >= 60800.00000000" in adql
    assert "p.time_bounds_lower <= 60840.00000000" in adql
    assert "energy_bandpassname = 'SPHEREx-D2'" in adql


def test_tap_adql_omits_time_without_window():
    adql = _tap_adql(210.8, 54.3, "SPHEREx-D2", "qr2")
    assert "time_bounds_lower >=" not in adql
    assert "time_bounds_lower <=" not in adql


def test_filter_records_by_time():
    records = [
        IrsaRecord(access_url="a", cutout_url="a", time_mjd=60810.0, bandpass="SPHEREx-D2"),
        IrsaRecord(access_url="b", cutout_url="b", time_mjd=60900.0, bandpass="SPHEREx-D2"),
        IrsaRecord(access_url="c", cutout_url="c", time_mjd=None, bandpass="SPHEREx-D2"),
    ]
    kept = filter_records_by_time(records, 60800.0, 60850.0)
    assert [item.access_url for item in kept] == ["a"]


class _ProxyError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "502 Server Error: Proxy Error for url: https://irsa.ipac.caltech.edu/TAP/sync"
        )
        self.code = 502


def _tap_table() -> Table:
    return Table(
        {
            "access_url": [ACCESS],
            "time_bounds_lower": [60810.0],
            "energy_bandpassname": ["SPHEREx-D2"],
        }
    )


class _Results:
    def to_table(self) -> Table:
        return _tap_table()


class _Service:
    def __init__(self, *, sync_failures: int, async_error: Exception | None = None) -> None:
        self.sync_failures = sync_failures
        self.async_error = async_error
        self.sync_calls = 0
        self.async_calls = 0
        self.async_timeout = None

    def search(self, adql: str) -> _Results:
        self.sync_calls += 1
        if self.sync_calls <= self.sync_failures:
            raise _ProxyError()
        return _Results()

    def run_async(self, adql: str, timeout: float | None = None) -> _Results:
        self.async_calls += 1
        self.async_timeout = timeout
        if self.async_error is not None:
            raise self.async_error
        return _Results()


def test_gateway_error_matches_irsa_proxy_502():
    assert _is_gateway_error(_ProxyError())
    assert not _is_gateway_error(RuntimeError("ADQL syntax error"))


def test_query_tap_retries_fast_502_then_uses_async(monkeypatch):
    service = _Service(sync_failures=2)
    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: service)
    monkeypatch.setattr("spherex_pipeline.irsa.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("spherex_pipeline.irsa.time.monotonic", lambda: 1.0)

    def http_must_not_run(adql: str) -> Table:
        raise AssertionError("un 502 de /TAP/sync no debe repetirse por HTTP")

    monkeypatch.setattr("spherex_pipeline.irsa._query_tap_http", http_must_not_run)
    records = query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert service.sync_calls == 2
    assert service.async_calls == 1
    assert service.async_timeout == 600
    assert len(records) == 1
    assert records[0].access_url == ACCESS


def test_query_tap_slow_502_skips_second_sync(monkeypatch):
    service = _Service(sync_failures=5)
    clock = {"t": 0.0}

    def monotonic() -> float:
        clock["t"] += 20.0
        return clock["t"]

    def http_must_not_run(adql: str) -> Table:
        raise AssertionError("un 502 de /TAP/sync no debe repetirse por HTTP")

    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: service)
    monkeypatch.setattr("spherex_pipeline.irsa.time.monotonic", monotonic)
    monkeypatch.setattr("spherex_pipeline.irsa._query_tap_http", http_must_not_run)
    records = query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert service.sync_calls == 1
    assert service.async_calls == 1
    assert len(records) == 1


def test_query_tap_fast_502_then_sync_succeeds(monkeypatch):
    service = _Service(sync_failures=1)
    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: service)
    monkeypatch.setattr("spherex_pipeline.irsa.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("spherex_pipeline.irsa.time.monotonic", lambda: 1.0)
    records = query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert service.sync_calls == 2
    assert service.async_calls == 0
    assert len(records) == 1


def test_query_tap_timeout_uses_async_not_another_sync(monkeypatch):
    class _Timeout(Exception):
        def __init__(self) -> None:
            super().__init__("HTTPSConnectionPool(host='irsa.ipac.caltech.edu'): Read timed out.")

    service = _Service(sync_failures=0)
    clock = {"t": 0.0}

    def monotonic() -> float:
        clock["t"] += 20.0
        return clock["t"]

    def search(adql: str):
        service.sync_calls += 1
        raise _Timeout()

    service.search = search  # type: ignore[method-assign]
    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: service)
    monkeypatch.setattr("spherex_pipeline.irsa.time.monotonic", monotonic)

    def http_must_not_run(adql: str) -> Table:
        raise AssertionError("un timeout de /TAP/sync no debe repetirse por HTTP")

    monkeypatch.setattr("spherex_pipeline.irsa._query_tap_http", http_must_not_run)
    records = query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert service.sync_calls == 1
    assert service.async_calls == 1
    assert len(records) == 1


def test_query_observations_uses_sia_and_skips_retired_qr2(monkeypatch):
    sia_records = [
        IrsaRecord(access_url=ACCESS.replace("/qr2/", "/dr1/"), cutout_url="u", time_mjd=60810.0, bandpass="SPHEREx-D2")
    ]

    def fake_sia(*args, **kwargs):
        assert kwargs.get("qr") == "dr1"
        return sia_records

    def tap_must_not_run(*args, **kwargs):
        raise AssertionError("con SIA de DR1 no hay que esperar al TAP")

    monkeypatch.setattr("spherex_pipeline.irsa.query_sia", fake_sia)
    monkeypatch.setattr("spherex_pipeline.irsa.query_tap", tap_must_not_run)
    from spherex_pipeline.irsa import query_observations

    records = query_observations(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert records == sia_records


def test_query_tap_non_gateway_pyvo_error_uses_http(monkeypatch):
    class _Broken:
        def search(self, adql: str):
            raise RuntimeError("pyvo no entiende el protocolo")

        def run_async(self, adql: str, timeout: float | None = None):
            raise AssertionError("no es un 502; no debe ir a async")

    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: _Broken())
    monkeypatch.setattr("spherex_pipeline.irsa._query_tap_http", lambda adql: _tap_table())
    records = query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert len(records) == 1


def test_query_tap_gateway_does_not_repeat_sync_over_http(monkeypatch):
    service = _Service(sync_failures=5, async_error=_ProxyError())
    monkeypatch.setattr("spherex_pipeline.irsa._pyvo_tap_service", lambda: service)
    monkeypatch.setattr("spherex_pipeline.irsa.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("spherex_pipeline.irsa.time.monotonic", lambda: 1.0)

    def http_must_not_run(adql: str) -> Table:
        raise AssertionError("no repetir /TAP/sync")

    monkeypatch.setattr("spherex_pipeline.irsa._query_tap_http", http_must_not_run)
    with pytest.raises(RuntimeError, match="No se pudo consultar TAP"):
        query_tap(210.8, 54.3, 0.05, qr="qr2", bandpass="SPHEREx-D2")
    assert service.async_calls == 1


def test_resolve_bandpass_rejects_mismatch_and_missing():
    with pytest.raises(ValueError, match="no coincide"):
        resolve_bandpass("SPHEREx-D2", detector=5)
    with pytest.raises(ValueError, match="Indique bandpass"):
        resolve_bandpass(None, None)
