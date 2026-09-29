"""Tests de errores controlados y de que IRSA no cae a demo."""

from unittest.mock import patch

import pytest

from spherex_pipeline.constants import DEMO_DEC, DEMO_RA, DEMO_SIZE_DEG
from spherex_pipeline.irsa import normalize_qr, resolve_bandpass
from spherex_pipeline.pipeline import get_observations, run_pipeline


def test_invalid_qr_and_bandpass_are_clear():
    with pytest.raises(ValueError, match="QR no reconocido"):
        normalize_qr("qr999")
    with pytest.raises(ValueError, match="bandpass no reconocido"):
        resolve_bandpass("INVALID")
    with pytest.raises(ValueError, match="QR no reconocido"):
        get_observations(DEMO_RA, DEMO_DEC, DEMO_SIZE_DEG, qr="qr999", source="demo")
    with pytest.raises(ValueError, match="bandpass"):
        get_observations(DEMO_RA, DEMO_DEC, DEMO_SIZE_DEG, bandpass="INVALID", source="demo")


def test_empty_irsa_returns_empty_list_not_demo():
    with patch("spherex_pipeline.pipeline.query_observations", return_value=[]):
        observations = get_observations(
            1.0, 2.0, 0.02, source="irsa", qr="qr2", bandpass="SPHEREx-D2"
        )
    assert observations == []


def test_irsa_failure_never_falls_back_to_demo():
    with patch("spherex_pipeline.pipeline.query_observations", side_effect=RuntimeError("TAP down")):
        with pytest.raises(RuntimeError, match="TAP down"):
            get_observations(DEMO_RA, DEMO_DEC, DEMO_SIZE_DEG, source="irsa")


def test_explicit_demo_is_labeled_demo(tmp_path):
    observations = get_observations(
        DEMO_RA,
        DEMO_DEC,
        DEMO_SIZE_DEG,
        source="demo",
        qr="qr2",
        bandpass="SPHEREx-D2",
        demo_dir=tmp_path,
    )
    assert len(observations) == 5
    assert all(obs.id.startswith("DEMO") for obs in observations)
    assert all(obs.metadata.get("source") == "demo" for obs in observations)


def test_run_pipeline_records_empty_retrieval():
    with patch("spherex_pipeline.pipeline.query_observations", return_value=[]):
        result = run_pipeline(0.0, 0.0, 0.02, source="irsa", qr="qr2", bandpass="SPHEREx-D2")
    assert result.report.tap_matches == 0
    assert result.report.requested == 0
    assert result.observations == []
