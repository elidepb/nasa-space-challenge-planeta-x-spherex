"""Dataset local de demostración con varias épocas de una misma región."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from spherex_pipeline.constants import (
    DEMO_BANDPASS,
    DEMO_DEC,
    DEMO_DETECTOR,
    DEMO_DIR,
    DEMO_N_EPOCHS,
    DEMO_NPIX,
    DEMO_PIXEL_SCALE_ARCSEC,
    DEMO_RA,
    DEMO_SIZE_DEG,
    DEMO_WAVELENGTH_UM,
    FLAG_BITS,
)
from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)

FIXED_SOURCES = (
    (16.0, 18.0, 4.5),
    (40.0, 22.0, 6.0),
    (28.0, 44.0, 3.2),
    (50.0, 50.0, 5.1),
    (12.0, 48.0, 2.8),
)
MOVING_START = (20.0, 24.0)
MOVING_STEP = (1.6, 0.9)
MOVING_FLUX = 8.0


def demo_catalog_path(demo_dir: Path | None = None) -> Path:
    return Path(demo_dir or DEMO_DIR) / "catalog.json"


def _spatial_wcs(ra: float, dec: float, npix: int) -> WCS:
    scale = DEMO_PIXEL_SCALE_ARCSEC / 3600.0
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [(npix + 1) / 2.0, (npix + 1) / 2.0]
    wcs.wcs.cdelt = [-scale, scale]
    wcs.wcs.radesys = "ICRS"
    wcs.wcs.equinox = 2000.0
    return wcs


def _gaussian(ny: int, nx: int, y0: float, x0: float, amplitude: float, sigma: float = 1.6) -> np.ndarray:
    yy, xx = np.mgrid[0:ny, 0:nx]
    return amplitude * np.exp(-(((yy - y0) ** 2) + ((xx - x0) ** 2)) / (2.0 * sigma**2))


def _build_epoch_arrays(epoch: int, npix: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    yy, xx = np.mgrid[0:npix, 0:npix]
    zodi = 18.0 + 0.04 * xx + 0.02 * yy
    image = zodi + rng.normal(0.0, 0.35, size=(npix, npix))
    for y0, x0, flux in FIXED_SOURCES:
        image += _gaussian(npix, npix, y0, x0, flux)

    mover_y = MOVING_START[0] + epoch * MOVING_STEP[0]
    mover_x = MOVING_START[1] + epoch * MOVING_STEP[1]
    image += _gaussian(npix, npix, mover_y, mover_x, MOVING_FLUX, sigma=1.4)

    flags = np.zeros((npix, npix), dtype=np.int32)
    flags[0, :] |= 1 << FLAG_BITS["REFERENCE"]
    flags[-1, :] |= 1 << FLAG_BITS["REFERENCE"]
    flags[:, 0] |= 1 << FLAG_BITS["REFERENCE"]
    flags[:, -1] |= 1 << FLAG_BITS["REFERENCE"]
    flags[32, 32] |= 1 << FLAG_BITS["NONFUNC"]
    flags[28, 36] |= 1 << FLAG_BITS["HOT"]
    image[32, 32] = np.nan

    variance = np.full((npix, npix), 0.12, dtype=np.float32)
    variance += 0.01 * np.abs(image - zodi)
    return {
        "image": image.astype(np.float32),
        "flags": flags,
        "variance": variance.astype(np.float32),
        "zodi": zodi.astype(np.float32),
    }


def _write_mef(
    path: Path,
    arrays: dict[str, np.ndarray],
    *,
    ra: float,
    dec: float,
    timestamp: str,
    obs_id: str,
    detector: int,
    wavelength_um: float,
) -> None:
    npix = arrays["image"].shape[0]
    wcs = _spatial_wcs(ra, dec, npix)
    header = wcs.to_header()
    header["EXTNAME"] = "IMAGE"
    header["BUNIT"] = "MJy / sr"
    header["DETECTOR"] = detector
    header["OBSID"] = obs_id
    header["DATE"] = timestamp
    header["DATE-OBS"] = timestamp
    header["TELESCOP"] = "SPHEREx"
    header["INSTRUME"] = "SPHEREx"
    header["BANDPASS"] = f"SPHEREx-D{detector}"
    header["WAVELEN"] = wavelength_um
    header["BANDWID"] = 0.05
    header["PSF_FWHM"] = 6.2

    primary = fits.PrimaryHDU()
    image = fits.ImageHDU(data=arrays["image"], header=header, name="IMAGE")
    flags = fits.ImageHDU(data=arrays["flags"], name="FLAGS")
    variance = fits.ImageHDU(data=arrays["variance"], name="VARIANCE")
    variance.header["BUNIT"] = "(MJy / sr)**2"
    zodi = fits.ImageHDU(data=arrays["zodi"], name="ZODI")
    zodi.header["BUNIT"] = "MJy / sr"
    psf = fits.ImageHDU(data=np.zeros((9, 21, 21), dtype=np.float32), name="PSF")

    wave_table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="X", format="2J", array=[[1, npix]]),
            fits.Column(name="Y", format="2J", array=[[1, npix]]),
            fits.Column(name="VALUES", format="2E", array=[[wavelength_um, 0.05]]),
        ]
    )
    wave_table.header["EXTNAME"] = "WCS-WAVE"

    fits.HDUList([primary, image, flags, variance, zodi, psf, wave_table]).writeto(path, overwrite=True)


def build_demo_dataset(
    output_dir: str | Path | None = None,
    n_epochs: int = DEMO_N_EPOCHS,
) -> Path:
    """Crea FITS demo de varias épocas y un catálogo JSON."""
    demo_dir = Path(output_dir or DEMO_DIR)
    demo_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    start = Time("2025-06-01T00:00:00", format="isot", scale="utc")

    catalog_obs: list[dict] = []
    for epoch in range(n_epochs):
        timestamp = (start + epoch * 45 * u.day).isot
        obs_id = f"DEMO-{epoch + 1:03d}"
        filename = f"epoch_{epoch + 1:03d}.fits"
        path = demo_dir / filename
        arrays = _build_epoch_arrays(epoch, DEMO_NPIX, rng)
        _write_mef(
            path,
            arrays,
            ra=DEMO_RA,
            dec=DEMO_DEC,
            timestamp=timestamp,
            obs_id=obs_id,
            detector=DEMO_DETECTOR,
            wavelength_um=DEMO_WAVELENGTH_UM,
        )
        catalog_obs.append(
            {
                "id": obs_id,
                "file": filename,
                "timestamp": timestamp,
                "ra": DEMO_RA,
                "dec": DEMO_DEC,
                "detector": DEMO_DETECTOR,
                "wavelength": DEMO_WAVELENGTH_UM,
                "bandpass": DEMO_BANDPASS,
            }
        )
        LOGGER.info("Escrito %s", path)

    catalog = {
        "region": {"ra": DEMO_RA, "dec": DEMO_DEC, "size": DEMO_SIZE_DEG},
        "bandpass": DEMO_BANDPASS,
        "pixel_scale_arcsec": DEMO_PIXEL_SCALE_ARCSEC,
        "npix": DEMO_NPIX,
        "notes": (
            "Dataset sintético con estructura MEF SPHEREx (IMAGE, FLAGS, "
            "VARIANCE, ZODI, PSF, WCS-WAVE). Incluye fuentes fijas y un "
            "objeto en movimiento para pruebas del motor científico."
        ),
        "observations": catalog_obs,
    }
    catalog_path = demo_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return catalog_path


def load_demo_observations(demo_dir: str | Path | None = None) -> list[Observation]:
    demo_dir = Path(demo_dir or DEMO_DIR)
    catalog_path = demo_dir / "catalog.json"
    if not catalog_path.exists():
        build_demo_dataset(demo_dir)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    observations: list[Observation] = []
    for row in catalog["observations"]:
        fits_path = demo_dir / row["file"]
        observations.append(
            observation_from_fits(
                fits_path,
                observation_id=row["id"],
                ra=row["ra"],
                dec=row["dec"],
                extra_metadata={
                    "bandpass": row.get("bandpass"),
                    "source": "demo",
                    "catalog": str(catalog_path),
                },
            )
        )
    return observations


def is_demo_region(ra: float, dec: float, size: float | None = None) -> bool:
    dra = (ra - DEMO_RA) * np.cos(np.deg2rad(DEMO_DEC))
    ddec = dec - DEMO_DEC
    distance = np.hypot(dra, ddec)
    if distance > 0.25:
        return False
    if size is not None and not (0.005 <= float(size) <= 0.3):
        return False
    return True
