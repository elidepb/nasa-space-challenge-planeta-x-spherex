"""Tests de lectura FITS y dataset demo."""

from astropy.io import fits

from spherex_pipeline.demo import build_demo_dataset
from spherex_pipeline.fits_reader import observation_from_fits


def test_demo_mef_has_spherex_extensions(tmp_path):
    catalog = build_demo_dataset(tmp_path, n_epochs=2)
    fits_path = tmp_path / "epoch_001.fits"
    assert catalog.exists()
    assert fits_path.exists()
    with fits.open(fits_path) as hdul:
        names = [hdu.name for hdu in hdul]
    for expected in ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE"):
        assert expected in names


def test_observation_extracts_contract_fields(tmp_path):
    build_demo_dataset(tmp_path, n_epochs=1)
    obs = observation_from_fits(tmp_path / "epoch_001.fits")
    assert obs.id.startswith("DEMO")
    assert obs.timestamp.startswith("2025-")
    assert obs.detector == 2
    assert obs.wavelength > 0
    assert obs.bandwidth == 0.05
    assert "WAVELEN" in (obs.wavelength_source or "")
    assert obs.spectral_calibration_quality == "approximate"
    assert obs.spectral_unit == "μm"
    assert obs.image.ndim == 2
    assert obs.flags is not None
    assert obs.variance is not None
    assert obs.zodi is not None
    assert obs.wcs() is not None
    summary = obs.to_summary()
    assert summary["fits_source"].endswith("epoch_001.fits")
    assert summary["spectral_calibration_quality"] == "approximate"
    assert summary["spectral_unit"] == "μm"
    contract = obs.to_contract()
    assert set(contract) >= {
        "id",
        "timestamp",
        "ra",
        "dec",
        "detector",
        "wavelength",
        "bandwidth",
        "wavelength_source",
        "bandwidth_source",
        "spectral_calibration_source",
        "spectral_calibration_quality",
        "spectral_unit",
        "image",
        "cutout",
        "fits_source",
        "metadata",
    }
