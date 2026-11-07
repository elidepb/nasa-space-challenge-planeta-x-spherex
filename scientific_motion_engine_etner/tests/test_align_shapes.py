from astro_pipeline.align import align_observations_to_reference
from astro_pipeline.mock import mock_observations


def test_align_observations_to_reference_equalizes_native_shapes():
    tall = mock_observations(shape=(80, 40), include_mover=False)[0]
    wide = mock_observations(shape=(50, 90), include_mover=False)[0]
    tall.id = "TALL"
    wide.id = "WIDE"
    assert tall.image.shape != wide.image.shape

    aligned = align_observations_to_reference([tall, wide])
    assert aligned[0].image.shape == aligned[1].image.shape == tall.image.shape
    assert aligned[0].wcs().to_header_string() == aligned[1].wcs().to_header_string()
