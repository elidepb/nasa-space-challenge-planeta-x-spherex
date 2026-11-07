"""Reproyecta una imagen a la cuadrícula WCS de referencia."""

from __future__ import annotations

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_interp


def reproject_to_grid(
    image: np.ndarray,
    variance: np.ndarray,
    wcs_in: WCS,
    wcs_ref: WCS,
    shape_ref: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if _same_grid(wcs_in, wcs_ref, image.shape, shape_ref):
        return image, variance

    aligned_image, footprint = reproject_interp((image, wcs_in), wcs_ref, shape_out=shape_ref)
    aligned_var, _ = reproject_interp((variance, wcs_in), wcs_ref, shape_out=shape_ref)
    out_of_bounds = (
        (footprint < 0.99)
        | ~np.isfinite(aligned_image)
        | ~np.isfinite(aligned_var)
    )
    aligned_image[out_of_bounds] = np.nan
    aligned_var[out_of_bounds] = np.nan
    return aligned_image, aligned_var


def _same_grid(
    wcs_in: WCS,
    wcs_ref: WCS,
    shape_in: tuple[int, ...],
    shape_ref: tuple[int, ...],
) -> bool:
    if shape_in != shape_ref:
        return False
    try:
        return wcs_in.to_header_string() == wcs_ref.to_header_string()
    except Exception:
        return False
