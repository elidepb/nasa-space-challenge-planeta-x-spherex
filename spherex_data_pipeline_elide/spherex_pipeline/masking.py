"""Máscara inicial de píxeles inválidos a partir de FLAGS SPHEREx."""

from __future__ import annotations

import numpy as np

from spherex_pipeline.constants import FLAG_BITS, INVALID_FLAG_NAMES


def invalid_flag_mask_value(flag_names: tuple[str, ...] = INVALID_FLAG_NAMES) -> int:
    """Devuelve la máscara binaria combinada de los bits inválidos."""
    combined = 0
    for name in flag_names:
        combined |= 1 << FLAG_BITS[name]
    return combined


def invalid_pixel_mask(
    flags: np.ndarray,
    flag_names: tuple[str, ...] = INVALID_FLAG_NAMES,
) -> np.ndarray:
    """True donde el píxel no debe usarse en análisis científico."""
    bits = invalid_flag_mask_value(flag_names)
    flags_int = np.asarray(flags, dtype=np.int64)
    return (flags_int & bits) != 0


def valid_pixel_mask(
    flags: np.ndarray,
    image: np.ndarray | None = None,
    variance: np.ndarray | None = None,
    flag_names: tuple[str, ...] = INVALID_FLAG_NAMES,
) -> np.ndarray:
    """True donde el píxel es usable: FLAGS OK y valores finitos."""
    valid = ~invalid_pixel_mask(flags, flag_names=flag_names)
    if image is not None:
        valid &= np.isfinite(image)
    if variance is not None:
        valid &= np.isfinite(variance) & (np.asarray(variance) >= 0)
    return valid


def apply_invalid_mask(
    image: np.ndarray,
    flags: np.ndarray,
    variance: np.ndarray | None = None,
    flag_names: tuple[str, ...] = INVALID_FLAG_NAMES,
) -> tuple[np.ndarray, np.ndarray]:
    """Pone NaN en píxeles inválidos y devuelve (imagen_enmascarada, valid_mask)."""
    mask = valid_pixel_mask(flags, image=image, variance=variance, flag_names=flag_names)
    masked = np.array(image, dtype=float, copy=True)
    masked[~mask] = np.nan
    return masked, mask
