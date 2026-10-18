"""Tests unitarios del cliente IRSA, sin red."""

import io
from email.message import EmailMessage
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from spherex_pipeline.irsa import (
    IrsaRecord,
    _tap_adql,
    cutout_url,
    download_record,
    filter_records_by_time,
    full_mef_url,
    normalize_qr,
    normalize_time_range,
    parse_time_bound,
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
        ("spherex_qr2", "qr2"),
        ("qr2_deep", "qr2_deep"),
    ],
)
def test_normalize_qr_aliases(value, expected):
    assert normalize_qr(value) == expected


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


def test_resolve_bandpass_rejects_mismatch_and_missing():
    with pytest.raises(ValueError, match="no coincide"):
        resolve_bandpass("SPHEREx-D2", detector=5)
    with pytest.raises(ValueError, match="Indique bandpass"):
        resolve_bandpass(None, None)
