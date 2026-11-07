"""Lee image, variance, valid_mask y wcs() del Observation de Elide."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from astro_pipeline.contracts import Observation


def ensure_spatial_wcs(observation: Observation) -> Observation:
    """Completa wcs_header si el camino spectral de Elide lo omitió."""
    if observation.wcs() is not None:
        return observation
    source = Path(str(observation.fits_source or ""))
    if not source.is_file():
        return observation
    with fits.open(source, memmap=True, ignore_missing_end=True) as hdul:
        image_hdu = hdul["IMAGE"] if "IMAGE" in hdul else hdul[1]
        wcs = WCS(image_hdu.header, naxis=2, relax=True)
        if wcs.naxis < 2:
            return observation
        observation.wcs_header = dict(wcs.to_header(relax=True))
    if observation.zodi is None:
        try:
            with fits.open(source, memmap=True, ignore_missing_end=True) as hdul:
                if "ZODI" in hdul and hdul["ZODI"].data is not None:
                    observation.zodi = np.array(hdul["ZODI"].data, dtype=float)
        except Exception:
            pass
    return observation


def read_scientific_arrays(
    observation: Observation,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, WCS, Time]:
    observation = ensure_spatial_wcs(observation)
    if observation.image is None:
        raise ValueError(f"Observation {observation.id!r} no trae image")

    image = np.array(observation.image, dtype=float, copy=True)
    wcs = observation.wcs()
    if wcs is None:
        raise ValueError(f"Observation {observation.id!r} no trae wcs()")

    valid = observation.valid_mask
    if valid is None:
        valid = np.isfinite(image)
        if observation.flags is not None:
            from spherex_pipeline.masking import valid_pixel_mask

            valid = valid_pixel_mask(
                observation.flags,
                image=image,
                variance=observation.variance,
            )
    valid = np.asarray(valid, dtype=bool)

    if observation.variance is not None:
        variance = np.array(observation.variance, dtype=float, copy=True)
    else:
        samples = image[valid]
        if samples.size:
            median = float(np.nanmedian(samples))
            mad = float(np.nanmedian(np.abs(samples - median)))
            sigma = 1.4826 * mad if mad > 0 else 1.0
        else:
            sigma = 1.0
        variance = np.full_like(image, sigma ** 2, dtype=float)

    valid = valid & np.isfinite(image) & np.isfinite(variance) & (variance > 0)
    epoch = _epoch(observation.timestamp)
    return image, variance, valid, wcs, epoch


def _epoch(timestamp: str) -> Time:
    if timestamp and timestamp != "unknown":
        for fmt in ("isot", None):
            try:
                return Time(timestamp, format=fmt, scale="utc") if fmt else Time(timestamp)
            except Exception:
                continue
    return Time(60800.0, format="mjd", scale="utc")
