"""Tests de get_observations sobre el dataset demo."""

from unittest.mock import patch

import pytest
import numpy as np

from spherex_pipeline.constants import DEMO_DEC, DEMO_RA, DEMO_SIZE_DEG
from spherex_pipeline.demo import build_demo_dataset
from spherex_pipeline.irsa import DownloadResult, IrsaRecord
from spherex_pipeline.pipeline import get_observations, run_pipeline


def test_get_observations_demo_is_chronological_and_homogeneous(tmp_path):
    observations = get_observations(
        DEMO_RA,
        DEMO_DEC,
        DEMO_SIZE_DEG,
        source="demo",
        qr="qr2",
        bandpass="SPHEREx-D2",
        demo_dir=tmp_path,
    )
    assert len(observations) >= 5
    timestamps = [obs.timestamp for obs in observations]
    assert timestamps == sorted(timestamps)
    shapes = {obs.image.shape for obs in observations}
    assert len(shapes) == 1
    first = observations[0]
    assert first.valid_mask is not None
    assert first.valid_mask.shape == first.image.shape
    assert np.isnan(first.image[~first.valid_mask]).all()
    assert int(np.sum(~first.valid_mask)) >= 1
    assert first.metadata.get("source") == "demo"
    assert first.metadata.get("qr") == "qr2"
    assert first.metadata.get("bandpass") == "SPHEREx-D2"


def test_get_observations_demo_honors_time_window(tmp_path):
    observations = get_observations(
        DEMO_RA,
        DEMO_DEC,
        DEMO_SIZE_DEG,
        source="demo",
        qr="qr2",
        bandpass="SPHEREx-D2",
        demo_dir=tmp_path,
        time_start="2025-06-01",
        time_end="2025-07-01",
    )
    assert len(observations) == 1
    assert observations[0].timestamp.startswith("2025-06-01")


def test_source_auto_is_rejected():
    with pytest.raises(ValueError, match="source debe ser"):
        get_observations(DEMO_RA, DEMO_DEC, DEMO_SIZE_DEG, source="auto")


def test_irsa_pipeline_records_mef_fallback(tmp_path):
    build_demo_dataset(tmp_path / "demo", n_epochs=1)
    fits_path = tmp_path / "demo" / "epoch_001.fits"
    record = IrsaRecord(
        access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/x/file.fits",
        cutout_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/x/file.fits?center=1,2&size=0.05",
        time_mjd=60810.0,
        bandpass="SPHEREx-D2",
        obs_id="FALLBACK1",
    )

    def fake_download(rec, cache_dir=None):
        return DownloadResult(path=fits_path, url=rec.access_url, kind="mef")

    with (
        patch("spherex_pipeline.pipeline.query_observations", return_value=[record]),
        patch("spherex_pipeline.pipeline.download_record", side_effect=fake_download),
    ):
        result = run_pipeline(
            DEMO_RA,
            DEMO_DEC,
            DEMO_SIZE_DEG,
            source="irsa",
            qr="qr2",
            bandpass="SPHEREx-D2",
            cache_dir=tmp_path / "cache",
            method="original",
        )

    assert result.report.mef_fallbacks == 1
    assert result.report.cutout_downloads == 0
    assert result.report.failed_downloads == 0
    assert len(result.observations) == 1
    assert result.observations[0].metadata["download_kind"] == "mef"


def test_run_pipeline_defaults_to_spectral_cutout(tmp_path):
    build_demo_dataset(tmp_path / "demo", n_epochs=1)
    fits_path = tmp_path / "demo" / "epoch_001.fits"
    record = IrsaRecord(
        access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/x/file.fits",
        cutout_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/x/file.fits?center=1,2&size=0.05",
        time_mjd=60810.0,
        bandpass="SPHEREx-D2",
        obs_id="SPEC1",
    )

    with (
        patch("spherex_pipeline.spectral_select.query_observations", return_value=[record]),
        patch("spherex_pipeline.spectral_select.download_cutout", return_value=fits_path),
    ):
        result = run_pipeline(
            DEMO_RA,
            DEMO_DEC,
            DEMO_SIZE_DEG,
            source="irsa",
            qr="qr2",
            bandpass="SPHEREx-D2",
            cache_dir=tmp_path / "cache",
            group=1,
        )

    assert result.query["method"] == "spectral"
    assert result.report.cutout_downloads == 1
    assert result.report.mef_fallbacks == 0
    assert len(result.observations) == 1
    assert result.observations[0].metadata.get("download_kind") == "cutout"


def test_method_must_be_spectral_or_original():
    with pytest.raises(ValueError, match="method debe ser"):
        run_pipeline(
            DEMO_RA,
            DEMO_DEC,
            DEMO_SIZE_DEG,
            source="demo",
            method="lean",
        )
