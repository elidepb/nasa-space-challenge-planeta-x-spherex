"""Prueba de aceptación contra NASA/IPAC IRSA.

Requiere red. Se ejecuta con:

    SPHEREX_IRSA=1 pytest tests/test_acceptance_irsa.py -q
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from spherex_pipeline.irsa import query_tap
from spherex_pipeline.pipeline import run_pipeline
from spherex_pipeline.validate import chronological_ok, contract_checks, duplicate_keys, qr_membership

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("SPHEREX_IRSA") != "1",
        reason="Prueba real IRSA: export SPHEREX_IRSA=1",
    ),
]

# M101, misma región del tutorial IRSA de cutouts SPHEREx.
QR = "qr2"
BANDPASS = "SPHEREx-D2"
RA = 210.80227
DEC = 54.34895
SIZE = 0.02
D2_WAVE_UM = (1.05, 1.70)


def test_tap_n_matches_get_observations_all_epochs():
    records = query_tap(RA, DEC, SIZE, qr=QR, bandpass=BANDPASS)
    n_tap = len(records)
    assert n_tap > 1, "Se necesitan varias épocas para validar el orden cronológico."

    result = run_pipeline(
        RA,
        DEC,
        SIZE,
        qr=QR,
        bandpass=BANDPASS,
        source="irsa",
        max_observations=None,
    )
    observations = result.observations
    report = result.report

    assert report.tap_matches == n_tap
    assert report.requested == n_tap
    assert report.downloaded == n_tap
    assert report.parsed == n_tap
    assert len(observations) == n_tap
    assert report.failed_downloads == 0
    assert report.failed_parses == 0
    assert report.duplicates == 0
    assert report.failures == []

    checks = contract_checks(observations)
    assert all(item.ok for item in checks.values())
    chrono_ok, out_of_order, _, _ = chronological_ok(observations)
    assert chrono_ok and out_of_order == 0
    assert duplicate_keys(observations) == []
    belong, other = qr_membership(observations, QR)
    assert belong == n_tap and other == 0
    assert all("qr2" in str(obs.fits_source) for obs in observations)
    assert all(obs.bandwidth is None or obs.bandwidth > 0 for obs in observations)
    assert all("WCS-WAVE" in (obs.wavelength_source or "") for obs in observations)
    assert all(obs.spectral_calibration_source == "WCS-WAVE" for obs in observations)
    assert all(obs.spectral_calibration_quality == "approximate" for obs in observations)
    assert all(obs.spectral_unit == "μm" for obs in observations)
    assert all(obs.metadata.get("spectral_calibration_source") == "WCS-WAVE" for obs in observations)
    assert all(obs.metadata.get("spectral_calibration_quality") == "approximate" for obs in observations)
    assert all(obs.metadata.get("spectral_unit") == "μm" for obs in observations)

    ras = {round(obs.ra, 6) for obs in observations}
    decs = {round(obs.dec, 6) for obs in observations}
    shapes = {obs.image.shape for obs in observations}
    assert ras == {round(RA, 6)}
    assert decs == {round(DEC, 6)}
    assert len(shapes) == 1

    timestamps = [obs.timestamp for obs in observations]
    assert all(ts and ts != "unknown" for ts in timestamps)
    assert timestamps == sorted(timestamps)

    wavelengths = [float(obs.wavelength) for obs in observations]
    assert all(np.isfinite(wave) for wave in wavelengths)
    assert all(D2_WAVE_UM[0] <= wave <= D2_WAVE_UM[1] for wave in wavelengths)
    assert len({round(wave, 6) for wave in wavelengths}) >= 1

    detectors = {int(obs.detector) for obs in observations}
    assert detectors == {2}
    assert all(obs.metadata.get("qr") == QR for obs in observations)
    assert all(obs.metadata.get("bandpass") == BANDPASS for obs in observations)
