"""Visitas SPHEREx con NAXIS distinto deben salir en un cuadrado común."""

from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from spherex_pipeline.cutouts import harmonize_to_region, wcs_contains_sky
from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.models import Observation

RA, DEC, SIZE = 210.80227, 54.34895, 0.85
ANGHELO_FITS = [
    Path("/home/elide-portocarrero/Descargas/level4_71a67fab6dd67c8c.fits"),
    Path("/home/elide-portocarrero/Descargas/level4_501e4964da1eb935.fits"),
    Path("/home/elide-portocarrero/Descargas/level4_42098d8b4289058b.fits"),
]


def _obs(oid: str, ny: int, nx: int, crval=(RA, DEC)) -> Observation:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [nx / 2.0, ny / 2.0]
    scale = 6.15 / 3600.0
    wcs.wcs.cdelt = [-scale, scale]
    wcs.wcs.crval = list(crval)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    image = np.ones((ny, nx), dtype=float)
    return Observation(
        id=oid,
        timestamp="2025-01-01T00:00:00",
        ra=crval[0],
        dec=crval[1],
        detector=2,
        wavelength=1.35,
        image=image,
        fits_source="test://irregular",
        variance=np.ones((ny, nx), dtype=float),
        zodi=np.zeros((ny, nx), dtype=float),
        flags=np.zeros((ny, nx), dtype=np.int32),
        valid_mask=np.ones((ny, nx), dtype=bool),
        cutout=image,
        wcs_header=dict(wcs.to_header()),
    )


def test_harmonize_makes_rectangular_visits_the_same_square():
    observations = [_obs("tall", 80, 40), _obs("wide", 40, 90), _obs("sq", 60, 60)]
    assert {obs.image.shape for obs in observations} != {observations[0].image.shape}
    out = harmonize_to_region(observations, RA, DEC, 0.15)
    shapes = {obs.image.shape for obs in out}
    assert len(shapes) == 1
    ny, nx = next(iter(shapes))
    assert ny == nx
    assert all(wcs_contains_sky(obs, RA, DEC) for obs in out)


@pytest.mark.skipif(not all(path.is_file() for path in ANGHELO_FITS), reason="FITS Level-4 de Anghelo no están en Descargas")
def test_anghelo_m101_level4_files_share_a_square():
    raw = [observation_from_fits(path, ra=RA, dec=DEC) for path in ANGHELO_FITS]
    native = {obs.image.shape for obs in raw}
    assert len(native) > 1
    out = harmonize_to_region(raw, RA, DEC, SIZE)
    shapes = {obs.image.shape for obs in out}
    assert len(shapes) == 1
    ny, nx = next(iter(shapes))
    assert ny == nx
    assert all(wcs_contains_sky(obs, RA, DEC) for obs in out)
