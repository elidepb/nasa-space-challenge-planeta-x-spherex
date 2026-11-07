"""Empareja pico positivo (t2) con pozo negativo (t1) y veta estrellas fijas."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from astro_pipeline.contracts import RejectionDiagnostics


@dataclass(frozen=True)
class DipoleMatch:
    peak_t1: dict[str, float]
    peak_t2: dict[str, float]
    dist_pix: float


def match_moving_dipoles(
    peaks_positive: list[dict[str, float]],
    peaks_negative: list[dict[str, float]],
    image_t1: np.ndarray,
    image_t2: np.ndarray,
    *,
    min_step_pixels: float = 1.3,
    max_step_pixels: float = 8.0,
    residual_sigma: float = 4.0,
) -> tuple[list[DipoleMatch], RejectionDiagnostics]:
    diagnostics = RejectionDiagnostics(
        peaks_positive=len(peaks_positive),
        peaks_negative=len(peaks_negative),
        min_step_pixels=min_step_pixels,
        max_step_pixels=max_step_pixels,
    )
    if not peaks_positive or not peaks_negative:
        return [], diagnostics

    possible: list[tuple[float, int, int]] = []
    for p_idx, pos in enumerate(peaks_positive):
        for n_idx, neg in enumerate(peaks_negative):
            dist_pix = float(np.hypot(pos["x"] - neg["x"], pos["y"] - neg["y"]))
            flux_ratio = pos["snr"] / neg["snr"] if neg["snr"] else np.inf
            if dist_pix < min_step_pixels:
                diagnostics.pairs_below_min_step += 1
                continue
            if dist_pix > max_step_pixels:
                diagnostics.pairs_above_max_step += 1
                continue
            if not (0.6 <= flux_ratio <= 1.67):
                diagnostics.pairs_flux_ratio += 1
                continue
            possible.append((dist_pix, p_idx, n_idx))

    possible.sort(key=lambda item: item[0])
    used_pos: set[int] = set()
    used_neg: set[int] = set()
    matches: list[DipoleMatch] = []

    for dist_pix, p_idx, n_idx in possible:
        if p_idx in used_pos or n_idx in used_neg:
            continue
        pos = peaks_positive[p_idx]
        neg = peaks_negative[n_idx]
        ix1, iy1 = int(round(neg["x"])), int(round(neg["y"]))
        ix2, iy2 = int(round(pos["x"])), int(round(pos["y"]))
        if image_t2[iy1, ix1] > residual_sigma or image_t1[iy2, ix2] > residual_sigma:
            diagnostics.pairs_anti_star_veto += 1
            continue
        used_pos.add(p_idx)
        used_neg.add(n_idx)
        matches.append(DipoleMatch(peak_t1=neg, peak_t2=pos, dist_pix=dist_pix))
    diagnostics.matched = len(matches)
    return matches, diagnostics
