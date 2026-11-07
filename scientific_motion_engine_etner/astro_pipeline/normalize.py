"""Normaliza fondo e intensidad con mediana y MAD sobre píxeles válidos."""

from __future__ import annotations

import numpy as np


def normalize_background(
    image: np.ndarray,
    variance: np.ndarray,
    valid_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    data = np.array(image, dtype=float, copy=True)
    var = np.array(variance, dtype=float, copy=True)
    bad = ~np.asarray(valid_mask, dtype=bool)
    data[bad] = np.nan
    var[bad] = np.nan

    background = np.nanmedian(data)
    mad = np.nanmedian(np.abs(data - background))
    scale = (1.4826 * mad) if mad > 0 else 1.0
    return (data - background) / scale, var / (scale ** 2)
