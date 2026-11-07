"""Reproyecta una imagen a la cuadrícula WCS de referencia."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_interp

from astro_pipeline.contracts import Observation
from astro_pipeline.read_observation import ensure_spatial_wcs, read_scientific_arrays


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


def align_observations_to_reference(observations: list[Observation]) -> list[Observation]:
    """Reproyecta todas las épocas al WCS y shape de la primera.

    El blink/resta visual necesita la misma grilla aunque los FITS nativos
    tengan NAXIS distintos (visitas SPHEREx de distinto footprint).
    """
    prepared = [ensure_spatial_wcs(obs) for obs in observations]
    refs = [obs for obs in prepared if obs.image is not None and obs.wcs() is not None]
    if not refs:
        return prepared
    ref = refs[0]
    ref_wcs = ref.wcs()
    shape_ref = ref.image.shape
    aligned: list[Observation] = []
    for obs in prepared:
        if obs.image is None or obs.wcs() is None:
            aligned.append(obs)
            continue
        image, variance, _valid, wcs, _epoch = read_scientific_arrays(obs)
        image, variance = reproject_to_grid(image, variance, wcs, ref_wcs, shape_ref)
        valid = np.isfinite(image) & np.isfinite(variance) & (variance > 0)
        zodi = None
        if obs.zodi is not None and np.asarray(obs.zodi).shape == obs.image.shape:
            zodi_al, _ = reproject_to_grid(
                np.asarray(obs.zodi, dtype=float),
                np.ones_like(obs.zodi, dtype=float),
                wcs,
                ref_wcs,
                shape_ref,
            )
            zodi = zodi_al
        aligned.append(
            replace(
                obs,
                image=image,
                variance=variance,
                valid_mask=valid,
                zodi=zodi,
                cutout=np.array(image, copy=True),
                wcs_header=dict(ref_wcs.to_header(relax=True)),
            )
        )
    return aligned


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
