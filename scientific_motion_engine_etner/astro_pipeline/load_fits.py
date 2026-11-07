"""Abre un FITS local con el lector de Elide y entrega su Observation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from astro_pipeline._paths import ensure_imports
from astro_pipeline.contracts import Observation

ensure_imports()

from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.masking import apply_invalid_mask


def load_spherex_observation(fits_path: str | Path) -> Observation:
    observation = observation_from_fits(fits_path)
    if observation.flags is not None:
        masked, valid = apply_invalid_mask(
            observation.image,
            observation.flags,
            variance=observation.variance,
        )
        observation.image = masked
        observation.valid_mask = valid
    elif observation.valid_mask is None and observation.image is not None:
        observation.valid_mask = np.isfinite(observation.image)
    return observation
