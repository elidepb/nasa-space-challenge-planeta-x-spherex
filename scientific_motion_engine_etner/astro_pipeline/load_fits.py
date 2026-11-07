"""Abre un FITS local con el lector de Elide y entrega su Observation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from astro_pipeline._paths import ensure_imports
from astro_pipeline.contracts import Observation

ensure_imports()

from spherex_pipeline.fits_reader import observation_from_fits
from spherex_pipeline.masking import apply_invalid_mask


def load_fits_region(
    fits_paths: list[str | Path],
    ra: float,
    dec: float,
    size_deg: float,
) -> list[Observation]:
    """Carga FITS locales y los deja en el mismo cuadrado de cielo.

    Anghelo debe usar esto (o get_observations de Elide) antes de comparar
    épocas: los Level-4 SPHEREx no comparten NAXIS entre visitas.
    """
    from spherex_pipeline.cutouts import harmonize_to_region

    observations = [load_spherex_observation(path) for path in fits_paths]
    prepared = []
    for observation in harmonize_to_region(observations, ra, dec, size_deg):
        if observation.flags is not None:
            masked, valid = apply_invalid_mask(
                observation.image,
                observation.flags,
                variance=observation.variance,
            )
            observation.image = masked
            observation.valid_mask = valid
        elif observation.image is not None:
            observation.valid_mask = np.isfinite(observation.image)
        prepared.append(observation)
    prepared.sort(key=lambda item: item.timestamp)
    return prepared


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
