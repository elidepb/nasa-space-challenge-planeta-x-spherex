"""Image differencing ponderado por varianza: SNR = (I2-I1)/sqrt(σ1²+σ2²)."""

from __future__ import annotations

import numpy as np


def snr_difference(
    image_t1: np.ndarray,
    variance_t1: np.ndarray,
    image_t2: np.ndarray,
    variance_t2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    diff = image_t2 - image_t1
    noise = np.sqrt(variance_t1 + variance_t2)
    valid = np.isfinite(diff) & np.isfinite(noise) & (noise > 0)
    snr_map = np.zeros_like(diff)
    snr_map[valid] = diff[valid] / noise[valid]
    return snr_map, valid
