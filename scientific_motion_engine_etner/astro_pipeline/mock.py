"""Observaciones sintéticas con el contrato Observation de Elide."""

from __future__ import annotations

from dataclasses import replace

from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import numpy as np

from astro_pipeline.contracts import Observation
from astro_pipeline.gaussian import smooth_gaussian_np


def mock_observations(
    *,
    shape: tuple[int, int] = (120, 120),
    object_xy: tuple[float, float] = (80.0, 60.0),
    shift_xy: tuple[float, float] = (3.0, 0.0),
    wavelength: float = 1.35,
    include_mover: bool = True,
    t2_wavelength: float | None = None,
) -> list[Observation]:
    star_xy = (40.0, 40.0)
    t1 = Time("2025-03-01T00:00:00", format="isot", scale="utc")
    t2 = Time("2025-09-01T00:00:00", format="isot", scale="utc")
    first = _one_observation(
        observation_id="MOCK-T1",
        timestamp=t1.isot,
        shape=shape,
        star_xy=star_xy,
        object_xy=object_xy if include_mover else None,
        wavelength=wavelength,
        seed=1,
    )
    second = _one_observation(
        observation_id="MOCK-T2",
        timestamp=t2.isot,
        shape=shape,
        star_xy=star_xy,
        object_xy=(
            (object_xy[0] + shift_xy[0], object_xy[1] + shift_xy[1])
            if include_mover
            else None
        ),
        wavelength=wavelength if t2_wavelength is None else t2_wavelength,
        seed=2,
    )
    return [first, second]


def inject_moving_source(
    observations: list[Observation],
    *,
    xy: tuple[float, float],
    shift_xy: tuple[float, float],
    amplitude: float = 350.0,
    sigma: float = 0.8,
) -> list[Observation]:
    """Planta un móvil en copias de las observaciones. El analizador no recibe xy."""
    planted: list[Observation] = []
    for index, obs in enumerate(observations):
        image = np.array(obs.image, copy=True, dtype=float)
        x = xy[0] + index * shift_xy[0]
        y = xy[1] + index * shift_xy[1]
        image += gaussian_stamp(image.shape, x, y, amplitude=amplitude, sigma=sigma)
        planted.append(replace(obs, image=image, cutout=np.array(image, copy=True)))
    return planted


def gaussian_stamp(
    shape: tuple[int, int],
    x: float,
    y: float,
    *,
    amplitude: float,
    sigma: float = 0.8,
) -> np.ndarray:
    yy, xx = np.indices(shape, dtype=float)
    return amplitude * np.exp(-0.5 * ((xx - x) ** 2 + (yy - y) ** 2) / sigma**2)


def create_mock_spherex_fits(
    filename: str,
    mjd: float,
    obj_xy: tuple,
    shift_wcs_px: tuple = (0.0, 0.0),
) -> None:
    shape = (120, 120)
    rng = np.random.default_rng(int(mjd))
    wcs = _plate_wcs(shape, shift_wcs_px=shift_wcs_px)
    header = wcs.to_header()
    header["MJD-AVG"] = mjd
    zodi = np.full(shape, 50.0, dtype=np.float32)
    noise_sigma = 2.0
    static_star = np.zeros(shape)
    static_star[60 - int(shift_wcs_px[1]), 60 - int(shift_wcs_px[0])] = 400.0
    static_star = smooth_gaussian_np(static_star, sigma=0.8)
    moving_obj = np.zeros(shape)
    ox = obj_xy[0] - int(shift_wcs_px[0])
    oy = obj_xy[1] - int(shift_wcs_px[1])
    moving_obj[oy, ox] = 350.0
    moving_obj = smooth_gaussian_np(moving_obj, sigma=0.8)
    image = (zodi + static_star + moving_obj + rng.normal(0.0, noise_sigma, shape)).astype(np.float32)
    variance = np.full(shape, noise_sigma ** 2, dtype=np.float32)
    flags = np.zeros(shape, dtype=np.int32)
    flags[10, 10] = 2
    image[10, 10] = 99999.0
    fits.HDUList([
        fits.PrimaryHDU(header=header),
        fits.ImageHDU(data=image, header=header, name="IMAGE"),
        fits.ImageHDU(data=variance, header=header, name="VARIANCE"),
        fits.ImageHDU(data=flags, header=header, name="FLAGS"),
        fits.ImageHDU(data=zodi, header=header, name="ZODI"),
    ]).writeto(filename, overwrite=True)


def _one_observation(
    *,
    observation_id: str,
    timestamp: str,
    shape: tuple[int, int],
    star_xy: tuple[float, float],
    object_xy: tuple[float, float] | None,
    wavelength: float,
    seed: int,
) -> Observation:
    rng = np.random.default_rng(seed)
    wcs = _plate_wcs(shape)
    zodi = np.full(shape, 50.0, dtype=float)
    noise_sigma = 2.0
    static_star = gaussian_stamp(shape, star_xy[0], star_xy[1], amplitude=400.0)
    moving = np.zeros(shape, dtype=float)
    if object_xy is not None:
        moving = gaussian_stamp(shape, object_xy[0], object_xy[1], amplitude=350.0)
    image = zodi + static_star + moving + rng.normal(0.0, noise_sigma, shape)
    variance = np.full(shape, noise_sigma ** 2, dtype=float)
    valid = np.ones(shape, dtype=bool)
    return Observation(
        id=observation_id,
        timestamp=timestamp,
        ra=150.0,
        dec=2.0,
        detector=2,
        wavelength=wavelength,
        image=image,
        fits_source="mock://elide-contract",
        metadata={"source": "mock", "bandpass": "SPHEREx-D2"},
        variance=variance,
        zodi=zodi,
        valid_mask=valid,
        cutout=np.array(image, copy=True),
        wcs_header=dict(wcs.to_header(relax=True)),
        bandwidth=0.04,
        wavelength_source="mock",
        spectral_calibration_source="mock",
    )


def _plate_wcs(
    shape: tuple[int, int],
    shift_wcs_px: tuple[float, float] = (0.0, 0.0),
) -> WCS:
    ny, nx = shape
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [nx / 2.0 + shift_wcs_px[0], ny / 2.0 + shift_wcs_px[1]]
    scale_deg = 6.15 / 3600.0
    wcs.wcs.cdelt = [-scale_deg, scale_deg]
    wcs.wcs.crval = [150.0, 2.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs
