"""Resta la extensión ZODI cuando Elide la entrega en Observation.zodi."""

from __future__ import annotations

import numpy as np


def subtract_zodi(image: np.ndarray, zodi: np.ndarray | None) -> np.ndarray:
    if zodi is None:
        return image
    zodi_arr = np.asarray(zodi, dtype=float)
    if zodi_arr.shape != image.shape:
        return image
    return image - zodi_arr
