"""Tests de get_observations sobre el dataset demo."""

import pytest
import numpy as np

from spherex_pipeline.constants import DEMO_DEC, DEMO_RA, DEMO_SIZE_DEG
from spherex_pipeline.pipeline import get_observations


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


def test_source_auto_is_rejected():
    with pytest.raises(ValueError, match="source debe ser"):
        get_observations(DEMO_RA, DEMO_DEC, DEMO_SIZE_DEG, source="auto")
