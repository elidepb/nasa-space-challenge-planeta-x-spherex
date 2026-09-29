"""Contrato Observation del pipeline SPHEREx."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from astropy.wcs import WCS

from spherex_pipeline.constants import SPECTRAL_CALIBRATION_QUALITY, SPECTRAL_UNIT


@dataclass
class Observation:
    """Observación SPHEREx normalizada para el resto del proyecto.

    Coincide con el contrato del README:
    id, timestamp, ra, dec, detector, wavelength, image/cutout,
    FITS source y metadata.  También expone FLAGS, VARIANCE, ZODI, WCS,
    bandwidth y la fuente espectral para el motor científico.
    """

    id: str
    timestamp: str
    ra: float
    dec: float
    detector: int | str
    wavelength: float
    image: np.ndarray
    fits_source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    flags: np.ndarray | None = None
    variance: np.ndarray | None = None
    zodi: np.ndarray | None = None
    valid_mask: np.ndarray | None = None
    cutout: np.ndarray | None = None
    wcs_header: dict[str, Any] | None = None
    bandwidth: float | None = None
    wavelength_source: str | None = None
    bandwidth_source: str | None = None
    spectral_calibration_source: str | None = None
    spectral_calibration_quality: str = SPECTRAL_CALIBRATION_QUALITY
    spectral_unit: str = SPECTRAL_UNIT

    def wcs(self) -> WCS | None:
        if not self.wcs_header:
            return None
        return WCS(self.wcs_header, relax=True)

    def to_contract(self) -> dict[str, Any]:
        """Diccionario in-memory con el contrato Observation."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "ra": float(self.ra),
            "dec": float(self.dec),
            "detector": self.detector,
            "wavelength": float(self.wavelength) if self.wavelength is not None else None,
            "bandwidth": None if self.bandwidth is None else float(self.bandwidth),
            "wavelength_source": self.wavelength_source,
            "bandwidth_source": self.bandwidth_source,
            "spectral_calibration_source": self.spectral_calibration_source,
            "spectral_calibration_quality": self.spectral_calibration_quality,
            "spectral_unit": self.spectral_unit,
            "image": self.image,
            "cutout": self.cutout if self.cutout is not None else self.image,
            "fits_source": self.fits_source,
            "metadata": self.metadata,
        }

    def to_summary(self) -> dict[str, Any]:
        """Resumen JSON-serializable, sin matrices científicas."""
        shape = None if self.image is None else list(self.image.shape)
        n_invalid = None
        if self.valid_mask is not None:
            n_invalid = int(np.size(self.valid_mask) - np.count_nonzero(self.valid_mask))
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "ra": float(self.ra),
            "dec": float(self.dec),
            "detector": self.detector,
            "wavelength": None if self.wavelength is None else round(float(self.wavelength), 6),
            "bandwidth": None if self.bandwidth is None else round(float(self.bandwidth), 6),
            "wavelength_source": self.wavelength_source,
            "bandwidth_source": self.bandwidth_source,
            "spectral_calibration_source": self.spectral_calibration_source,
            "spectral_calibration_quality": self.spectral_calibration_quality,
            "spectral_unit": self.spectral_unit,
            "fits_source": self.fits_source,
            "shape": shape,
            "n_invalid_pixels": n_invalid,
            "metadata": {
                key: value
                for key, value in self.metadata.items()
                if _is_jsonable(value)
            },
        }

    def product_key(self) -> tuple[str, str, str]:
        url = str(self.metadata.get("access_url") or self.fits_source).split("?")[0]
        return (url, str(self.timestamp), str(self.detector))

    def __repr__(self) -> str:
        shape = None if self.image is None else self.image.shape
        return (
            f"Observation(id={self.id!r}, timestamp={self.timestamp!r}, "
            f"detector={self.detector!r}, wavelength={self.wavelength!r}, shape={shape})"
        )


def _is_jsonable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))
