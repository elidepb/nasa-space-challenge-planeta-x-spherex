"""Tests unitarios del cliente IRSA, sin red."""

import pytest

from spherex_pipeline.irsa import (
    IrsaRecord,
    cutout_url,
    normalize_qr,
    resolve_bandpass,
    subsample_epochs,
)


def test_cutout_url_appends_center_and_size():
    url = cutout_url(
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/file.fits",
        210.8,
        54.3,
        0.05,
    )
    assert url.endswith("file.fits?center=210.8,54.3&size=0.05")


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


def test_resolve_bandpass_rejects_mismatch_and_missing():
    with pytest.raises(ValueError, match="no coincide"):
        resolve_bandpass("SPHEREx-D2", detector=5)
    with pytest.raises(ValueError, match="Indique bandpass"):
        resolve_bandpass(None, None)
