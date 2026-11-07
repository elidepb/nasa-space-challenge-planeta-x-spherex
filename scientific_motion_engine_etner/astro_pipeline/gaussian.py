"""Filtro gaussiano 2D separable (solo presentación y FITS sintéticos)."""

from __future__ import annotations

import numpy as np


def smooth_gaussian_np(img: np.ndarray, sigma: float = 0.8) -> np.ndarray:
    radius = max(1, int(round(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=float)
    kernel_1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel_1d /= np.sum(kernel_1d)
    clean = np.nan_to_num(img, nan=0.0)
    temp = np.apply_along_axis(lambda row: np.convolve(row, kernel_1d, mode="same"), axis=1, arr=clean)
    return np.apply_along_axis(lambda col: np.convolve(col, kernel_1d, mode="same"), axis=0, arr=temp)
