"""Tests de la máscara de FLAGS SPHEREx."""

import numpy as np

from spherex_pipeline.constants import FLAG_BITS
from spherex_pipeline.masking import apply_invalid_mask, invalid_pixel_mask, valid_pixel_mask


def test_hot_and_nonfunc_pixels_are_invalid():
    flags = np.zeros((4, 4), dtype=np.int32)
    flags[1, 1] = 1 << FLAG_BITS["HOT"]
    flags[2, 2] = 1 << FLAG_BITS["NONFUNC"]
    mask = invalid_pixel_mask(flags)
    assert mask[1, 1]
    assert mask[2, 2]
    assert not mask[0, 0]


def test_source_bit_is_not_invalid():
    flags = np.zeros((2, 2), dtype=np.int32)
    flags[0, 0] = 1 << FLAG_BITS["SOURCE"]
    assert not invalid_pixel_mask(flags)[0, 0]


def test_apply_invalid_mask_sets_nan_and_rejects_nonfinite():
    image = np.ones((3, 3), dtype=float)
    image[0, 1] = np.inf
    flags = np.zeros((3, 3), dtype=np.int32)
    flags[1, 1] = 1 << FLAG_BITS["OVERFLOW"]
    masked, valid = apply_invalid_mask(image, flags)
    assert np.isnan(masked[1, 1])
    assert np.isnan(masked[0, 1])
    assert valid[2, 2]
    assert valid_pixel_mask(flags, image=image)[2, 2]
