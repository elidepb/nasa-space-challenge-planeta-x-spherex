"""Cutouts homogéneos de una misma región del cielo."""

from __future__ import annotations

import logging

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.nddata import Cutout2D
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales, skycoord_to_pixel

from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)


def _pixel_scale_deg(wcs: WCS) -> float:
    scales = proj_plane_pixel_scales(wcs)
    return float(np.mean(np.abs(scales)))


def target_npix(wcs: WCS, size_deg: float) -> int:
    scale = _pixel_scale_deg(wcs)
    if scale <= 0:
        return 32
    return max(8, int(np.ceil(size_deg / scale)))


def shared_target_npix(observations: list[Observation], size_deg: float) -> int:
    """Un solo npix para todas las épocas, para que el blink no mezcle tamaños."""
    scales = []
    for observation in observations:
        wcs = observation.wcs()
        if wcs is None:
            continue
        scale = _pixel_scale_deg(wcs)
        if scale > 0:
            scales.append(scale)
    if not scales:
        return max(8, int(np.ceil(size_deg / (6.15 / 3600.0))))
    return max(8, int(np.ceil(size_deg / float(np.median(scales)))))


def _cut_array(array: np.ndarray | None, cutout: Cutout2D, fill) -> np.ndarray | None:
    if array is None:
        return None
    out = np.full(cutout.shape, fill, dtype=array.dtype)
    dest = getattr(cutout, "slices_cutout", None) or cutout.slices_copy
    out[dest] = array[cutout.slices_original]
    return out


def cutout_region(
    observation: Observation,
    ra: float,
    dec: float,
    size_deg: float,
    npix: int | None = None,
) -> Observation:
    """Recorta la observación a un cuadrado de `npix` centrado en (ra, dec).

    Los FITS SPHEREx de distintas visitas no tienen el mismo NAXIS: el recorte
    IBE es la intersección del cono con el detector. Sin este paso el visor
    no puede comparar épocas (tamaños distintos / franja negra).
    """
    wcs = observation.wcs()
    if wcs is None or observation.image is None:
        LOGGER.warning("Cutout omitido para %s: falta WCS o image", observation.id)
        return observation

    npix = int(npix) if npix is not None else target_npix(wcs, size_deg)
    position = SkyCoord(ra=ra, dec=dec, unit="deg", frame="icrs")
    try:
        image_cut = Cutout2D(
            observation.image,
            position=position,
            size=(npix, npix),
            wcs=wcs,
            mode="partial",
            fill_value=np.nan,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Cutout2D no aplicable a %s: %s", observation.id, exc)
        return observation

    observation.image = np.array(image_cut.data, dtype=float)
    observation.cutout = np.array(image_cut.data, dtype=float)
    observation.flags = _cut_array(observation.flags, image_cut, fill=0)
    observation.variance = _cut_array(observation.variance, image_cut, fill=np.nan)
    observation.zodi = _cut_array(observation.zodi, image_cut, fill=np.nan)
    observation.valid_mask = _cut_array(observation.valid_mask, image_cut, fill=False)
    observation.wcs_header = dict(image_cut.wcs.to_header(relax=True))
    observation.ra = float(ra)
    observation.dec = float(dec)
    observation.metadata["cutout_npix"] = npix
    observation.metadata["cutout_size_deg"] = float(size_deg)
    return observation


def harmonize_to_region(
    observations: list[Observation],
    ra: float,
    dec: float,
    size_deg: float,
) -> list[Observation]:
    """Deja todas las épocas en el mismo cuadrado de cielo (mismo npix)."""
    if not observations:
        return observations
    npix = shared_target_npix(observations, size_deg)
    cut = [cutout_region(obs, ra, dec, size_deg, npix=npix) for obs in observations]
    return homogenize_shapes(cut)


def homogenize_shapes(observations: list[Observation]) -> list[Observation]:
    """Rellena las matrices para que todas tengan la misma forma."""
    if not observations:
        return observations

    max_ny = max(obs.image.shape[0] for obs in observations if obs.image is not None)
    max_nx = max(obs.image.shape[1] for obs in observations if obs.image is not None)
    target = (max_ny, max_nx)

    for obs in observations:
        obs.image = _pad(obs.image, target, np.nan)
        obs.cutout = _pad(obs.cutout if obs.cutout is not None else obs.image, target, np.nan)
        if obs.flags is not None:
            obs.flags = _pad(obs.flags, target, 0)
        if obs.variance is not None:
            obs.variance = _pad(obs.variance, target, np.nan)
        if obs.zodi is not None:
            obs.zodi = _pad(obs.zodi, target, np.nan)
        if obs.valid_mask is not None:
            obs.valid_mask = _pad(obs.valid_mask, target, False)
        obs.metadata["shape"] = list(target)
    return observations


def wcs_contains_sky(
    observation: Observation,
    ra: float,
    dec: float,
    margin_pix: float = 0.5,
) -> bool:
    """True si (ra, dec) cae dentro de los píxeles del cutout."""
    wcs = observation.wcs()
    if wcs is None or observation.image is None:
        return False
    try:
        x, y = skycoord_to_pixel(
            SkyCoord(ra=ra, dec=dec, unit="deg", frame="icrs"),
            wcs,
            origin=0,
        )
    except Exception:  # noqa: BLE001
        return False
    ny, nx = observation.image.shape[-2:]
    return (-margin_pix <= float(x) < nx + margin_pix) and (
        -margin_pix <= float(y) < ny + margin_pix
    )


def _pad(array: np.ndarray, shape: tuple[int, int], fill) -> np.ndarray:
    if array.shape == shape:
        return array
    out = np.full(shape, fill, dtype=array.dtype)
    ny = min(array.shape[0], shape[0])
    nx = min(array.shape[1], shape[1])
    out[:ny, :nx] = array[:ny, :nx]
    return out
