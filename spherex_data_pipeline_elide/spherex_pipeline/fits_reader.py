"""Lectura de MEF SPHEREx y extracción de extensiones científicas."""

from __future__ import annotations

import logging
import re
import warnings
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from spherex_pipeline.constants import (
    DETECTOR_WAVELENGTH_UM,
    SPECTRAL_CALIBRATION_QUALITY,
    SPECTRAL_CALIBRATION_SOURCE_WCS_WAVE,
    SPECTRAL_UNIT,
)
from spherex_pipeline.models import Observation

LOGGER = logging.getLogger(__name__)

DETECTOR_IN_NAME = re.compile(r"(\d)D(\d)", re.IGNORECASE)
HEADER_META_KEYS = (
    "OBSID",
    "DATE",
    "DATE-OBS",
    "DETECTOR",
    "BUNIT",
    "TELAPSE",
    "EXPTIME",
    "PSF_FWHM",
    "OBJECT",
    "TELESCOP",
    "INSTRUME",
    "FILTER",
    "BANDPASS",
    "WAVELEN",
    "BANDWID",
)


def _hdu_by_name(hdulist: fits.HDUList, name: str) -> fits.ImageHDU | None:
    try:
        return hdulist[name]
    except (KeyError, TypeError, IndexError):
        return None


def _array_or_none(hdulist: fits.HDUList, name: str) -> np.ndarray | None:
    hdu = _hdu_by_name(hdulist, name)
    if hdu is None or hdu.data is None:
        return None
    return np.array(hdu.data)


def _spatial_wcs(header: fits.Header) -> WCS | None:
    try:
        wcs = WCS(header, naxis=2, relax=True)
        if wcs.naxis < 2:
            return None
        return wcs
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("No se pudo construir WCS espacial: %s", exc)
        return None


def _wcs_header_dict(wcs: WCS | None, header: fits.Header) -> dict[str, Any]:
    if wcs is not None:
        try:
            return dict(wcs.to_header(relax=True))
        except Exception:  # noqa: BLE001
            pass
    keys = [key for key in header if key.startswith(("CTYPE", "CRVAL", "CRPIX", "CDELT", "CUNIT", "CD", "PC", "NAXIS", "EQUINOX", "RADESYS"))]
    return {key: header[key] for key in keys}


def _detector_from_header_or_name(header: fits.Header, source: str) -> int | str:
    if "DETECTOR" in header:
        try:
            return int(header["DETECTOR"])
        except (TypeError, ValueError):
            return str(header["DETECTOR"])
    match = DETECTOR_IN_NAME.search(Path(str(source)).name)
    if match:
        return int(match.group(2))
    return "unknown"


def _timestamp_from_header(header: fits.Header, fallback_mjd: float | None = None) -> str:
    for key in ("DATE-OBS", "DATE", "OBS-DATE"):
        if key in header and header[key]:
            raw = str(header[key]).strip()
            try:
                return Time(raw, format="isot", scale="utc").isot
            except Exception:  # noqa: BLE001
                try:
                    return Time(raw).isot
                except Exception:  # noqa: BLE001
                    return raw
    if fallback_mjd is not None and np.isfinite(fallback_mjd):
        return Time(fallback_mjd, format="mjd", scale="utc").isot
    return "unknown"


def _quantity_to_um(value: Any) -> float:
    if hasattr(value, "to"):
        return float(value.to(u.um).value)
    number = float(np.asarray(value).reshape(-1)[0])
    if number > 100:
        return number / 1e4
    if number > 20:
        return number / 1e3
    return number


@dataclass
class SpectralSample:
    wavelength_um: float | None
    bandwidth_um: float | None
    wavelength_source: str
    bandwidth_source: str | None


def _spectral_calibration_source(source: str | None) -> str:
    text = source or ""
    if "WCS-WAVE" in text:
        return SPECTRAL_CALIBRATION_SOURCE_WCS_WAVE
    if "CWAVE" in text:
        return "CWAVE"
    if "CBAND" in text:
        return "CBAND"
    if "WAVELEN" in text or "IMAGE header" in text:
        return "IMAGE-HEADER"
    if "detector nominal" in text:
        return "DETECTOR-NOMINAL"
    if "fallback" in text:
        return "FALLBACK"
    return text or "unavailable"


def _wavelength_from_wcs_wave(hdulist: fits.HDUList, header: fits.Header) -> SpectralSample | None:
    image_hdu = _hdu_by_name(hdulist, "IMAGE") or hdulist[1]
    if image_hdu is None or image_hdu.data is None:
        return None
    try:
        ny, nx = image_hdu.data.shape[-2:]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            spectral = WCS(header=image_hdu.header, fobj=hdulist, key="W")
        spectral.sip = None
        world = spectral.pixel_to_world(nx / 2.0 - 0.5, ny / 2.0 - 0.5)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("WCS espectral no disponible: %s", exc)
        return None

    wavelength = None
    bandwidth = None
    if isinstance(world, (list, tuple)):
        if len(world) >= 1:
            wavelength = _quantity_to_um(world[0])
        if len(world) >= 2:
            bandwidth = _quantity_to_um(world[1])
    else:
        spectral_coord = getattr(world, "wavelength", world)
        wavelength = _quantity_to_um(spectral_coord)
        extra = getattr(world, "bandwidth", None)
        if extra is not None:
            bandwidth = _quantity_to_um(extra)

    if wavelength is None or not np.isfinite(wavelength) or wavelength <= 0:
        return None
    source = "WCS-WAVE (IMAGE WCS key=W, píxel central del cutout)"
    return SpectralSample(
        wavelength_um=wavelength,
        bandwidth_um=bandwidth if bandwidth is not None and np.isfinite(bandwidth) else None,
        wavelength_source=source,
        bandwidth_source=source if bandwidth is not None else None,
    )


def _wavelength_from_cwave(hdulist: fits.HDUList) -> SpectralSample | None:
    cwave_hdu = _hdu_by_name(hdulist, "CWAVE")
    if cwave_hdu is None or cwave_hdu.data is None:
        return None
    data = np.asarray(cwave_hdu.data, dtype=float)
    ny, nx = data.shape[-2:]
    wavelength = _quantity_to_um(data[..., ny // 2, nx // 2])
    bandwidth = None
    bandwidth_source = None
    cband_hdu = _hdu_by_name(hdulist, "CBAND")
    if cband_hdu is not None and cband_hdu.data is not None:
        band = np.asarray(cband_hdu.data, dtype=float)
        bandwidth = _quantity_to_um(band[..., ny // 2, nx // 2])
        bandwidth_source = "CBAND (píxel central)"
    if not np.isfinite(wavelength) or wavelength <= 0:
        return None
    return SpectralSample(
        wavelength_um=wavelength,
        bandwidth_um=bandwidth,
        wavelength_source="CWAVE (píxel central)",
        bandwidth_source=bandwidth_source,
    )


def extract_spectral(
    hdulist: fits.HDUList,
    header: fits.Header,
    detector: int | str,
    fallback: float | None = None,
) -> SpectralSample:
    """λ y Δλ del producto. CWAVE/CBAND se usan solo si existen en el MEF."""
    sample = _wavelength_from_cwave(hdulist)
    if sample is not None:
        return sample
    sample = _wavelength_from_wcs_wave(hdulist, header)
    if sample is not None:
        return sample

    wavelength = None
    wavelength_source = "unavailable"
    for key in ("CWAVE", "WAVELEN", "WAVE", "WAVELNTH"):
        if key in header:
            try:
                wavelength = float(header[key])
                wavelength_source = f"IMAGE header {key}"
                break
            except (TypeError, ValueError):
                continue
    bandwidth = None
    bandwidth_source = None
    for key in ("CBAND", "BANDWID", "BANDWIDTH"):
        if key in header:
            try:
                bandwidth = float(header[key])
                bandwidth_source = f"IMAGE header {key}"
                break
            except (TypeError, ValueError):
                continue

    if wavelength is None:
        if fallback is not None:
            wavelength = float(fallback)
            wavelength_source = "fallback argument"
        elif isinstance(detector, int) and detector in DETECTOR_WAVELENGTH_UM:
            wavelength = DETECTOR_WAVELENGTH_UM[detector]
            wavelength_source = "detector nominal (último recurso)"

    return SpectralSample(
        wavelength_um=wavelength,
        bandwidth_um=bandwidth,
        wavelength_source=wavelength_source,
        bandwidth_source=bandwidth_source,
    )


def _relevant_metadata(header: fits.Header) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key in HEADER_META_KEYS:
        if key in header:
            value = header[key]
            meta[key] = value.decode() if isinstance(value, bytes) else value
    return meta


def extract_extensions(hdulist: fits.HDUList) -> dict[str, Any]:
    """Extrae IMAGE, FLAGS, VARIANCE, ZODI, WCS y metadatos de un MEF."""
    image_hdu = _hdu_by_name(hdulist, "IMAGE")
    if image_hdu is None or image_hdu.data is None:
        image_hdu = next(
            (hdu for hdu in hdulist[1:] if getattr(hdu, "data", None) is not None and hdu.data.ndim >= 2),
            None,
        )
    if image_hdu is None:
        raise ValueError("El FITS no contiene una extensión de imagen científica.")

    header = image_hdu.header
    wcs = _spatial_wcs(header)
    return {
        "image": np.array(image_hdu.data, dtype=float),
        "flags": _array_or_none(hdulist, "FLAGS"),
        "variance": _array_or_none(hdulist, "VARIANCE"),
        "zodi": _array_or_none(hdulist, "ZODI"),
        "wcs": wcs,
        "wcs_header": _wcs_header_dict(wcs, header),
        "header": header,
        "image_hdu": image_hdu,
    }


def observation_from_fits(
    path_or_url: str | Path,
    *,
    observation_id: str | None = None,
    ra: float | None = None,
    dec: float | None = None,
    timestamp_mjd: float | None = None,
    wavelength_fallback: float | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Observation:
    """Abre un FITS SPHEREx y construye un Observation (aún sin máscara)."""
    source = str(path_or_url)
    with fits.open(source, memmap=False) as hdulist:
        extracted = extract_extensions(hdulist)
        header = extracted["header"]
        detector = _detector_from_header_or_name(header, source)
        timestamp = _timestamp_from_header(header, fallback_mjd=timestamp_mjd)
        spectral = extract_spectral(hdulist, header, detector, fallback=wavelength_fallback)

        wcs = extracted["wcs"]
        if ra is None or dec is None:
            if wcs is not None and wcs.wcs.crval is not None:
                ra = float(wcs.wcs.crval[0]) if ra is None else ra
                dec = float(wcs.wcs.crval[1]) if dec is None else dec

        obs_id = observation_id or str(header.get("OBSID") or Path(source).stem)
        metadata = _relevant_metadata(header)
        metadata.update(extra_metadata or {})
        if extracted["variance"] is not None:
            metadata["has_variance"] = True
        if extracted["zodi"] is not None:
            metadata["has_zodi"] = True
        if extracted["flags"] is not None:
            metadata["has_flags"] = True
        metadata["bunit"] = str(header.get("BUNIT", "MJy / sr"))
        metadata["wavelength_source"] = spectral.wavelength_source
        metadata["bandwidth_source"] = spectral.bandwidth_source
        cal_source = _spectral_calibration_source(spectral.wavelength_source)
        metadata["spectral_calibration_source"] = cal_source
        metadata["spectral_calibration_quality"] = SPECTRAL_CALIBRATION_QUALITY
        metadata["spectral_unit"] = SPECTRAL_UNIT

        cutout = np.array(extracted["image"], copy=True)
        return Observation(
            id=str(obs_id),
            timestamp=timestamp,
            ra=float(ra if ra is not None else np.nan),
            dec=float(dec if dec is not None else np.nan),
            detector=detector,
            wavelength=float(spectral.wavelength_um) if spectral.wavelength_um is not None else float("nan"),
            image=cutout,
            fits_source=source,
            metadata=metadata,
            flags=extracted["flags"],
            variance=extracted["variance"],
            zodi=extracted["zodi"],
            cutout=cutout,
            wcs_header=extracted["wcs_header"],
            bandwidth=spectral.bandwidth_um,
            wavelength_source=spectral.wavelength_source,
            bandwidth_source=spectral.bandwidth_source,
            spectral_calibration_source=cal_source,
            spectral_calibration_quality=SPECTRAL_CALIBRATION_QUALITY,
            spectral_unit=SPECTRAL_UNIT,
        )
