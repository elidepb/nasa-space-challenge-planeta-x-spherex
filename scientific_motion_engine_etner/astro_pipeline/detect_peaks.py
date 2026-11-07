"""Detecta máximos locales en un mapa de SNR."""

from __future__ import annotations

import numpy as np


def detect_snr_peaks(
    snr_image: np.ndarray,
    valid_mask: np.ndarray,
    threshold: float = 6.0,
) -> list[dict[str, float]]:
    clean_snr = np.nan_to_num(snr_image, nan=0.0)
    ny, nx = clean_snr.shape
    ys, xs = np.where((clean_snr >= threshold) & valid_mask)
    sources: list[dict[str, float]] = []

    for y, x in zip(ys, xs):
        if y < 6 or y >= ny - 6 or x < 6 or x >= nx - 6:
            continue
        if not np.all(valid_mask[y - 2:y + 3, x - 2:x + 3]):
            continue

        value = clean_snr[y, x]
        patch_5x5 = clean_snr[y - 2:y + 3, x - 2:x + 3]
        if value < np.max(patch_5x5):
            continue
        if np.sum(patch_5x5 == value) > 1:
            max_y, max_x = np.argwhere(patch_5x5 == value)[0]
            if max_y != 2 or max_x != 2:
                continue

        patch_3x3 = np.maximum(clean_snr[y - 1:y + 2, x - 1:x + 2], 0.0)
        total_w = np.sum(patch_3x3)
        if total_w <= 0:
            continue
        gy, gx = np.mgrid[y - 1:y + 2, x - 1:x + 2]
        sources.append({
            "x": float(np.sum(gx * patch_3x3) / total_w),
            "y": float(np.sum(gy * patch_3x3) / total_w),
            "snr": float(value),
        })
    return sources
