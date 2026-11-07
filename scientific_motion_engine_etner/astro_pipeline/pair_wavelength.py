"""Empareja visitas de λ parecida en épocas distintas (contrato Elide)."""

from __future__ import annotations

import numpy as np

from astro_pipeline.contracts import Observation

DEFAULT_MAX_DELTA_UM = 0.05


def group_comparable_epochs(
    observations: list[Observation],
    *,
    max_delta_um: float = DEFAULT_MAX_DELTA_UM,
) -> list[list[Observation]]:
    usable = [
        obs
        for obs in observations
        if obs.image is not None and obs.wcs() is not None
    ]
    groups: list[list[Observation]] = []
    ordered = sorted(
        usable,
        key=lambda obs: (_wavelength(obs), str(obs.timestamp), obs.id),
    )
    for obs in ordered:
        placed = False
        for group in groups:
            if _same_channel(group[0], obs, max_delta_um=max_delta_um):
                group.append(obs)
                placed = True
                break
        if not placed:
            groups.append([obs])
    return [
        sorted(group, key=lambda obs: (str(obs.timestamp), obs.id))
        for group in groups
        if len(group) >= 2
    ]


def pair_comparable_epochs(
    observations: list[Observation],
    *,
    max_delta_um: float = DEFAULT_MAX_DELTA_UM,
) -> list[tuple[Observation, Observation]]:
    pairs: list[tuple[Observation, Observation]] = []
    for group in group_comparable_epochs(observations, max_delta_um=max_delta_um):
        pairs.extend(zip(group, group[1:]))
    return pairs


def _wavelength(obs: Observation) -> float:
    value = obs.wavelength
    if value is None or not np.isfinite(value):
        return 0.0
    return float(value)


def _same_channel(
    ref: Observation,
    other: Observation,
    *,
    max_delta_um: float,
) -> bool:
    ref_wl = ref.wavelength
    other_wl = other.wavelength
    if str(ref.detector) != str(other.detector):
        return False
    if (
        ref_wl is None
        or other_wl is None
        or not np.isfinite(ref_wl)
        or not np.isfinite(other_wl)
    ):
        return True

    tolerance = max_delta_um
    for bandwidth in (ref.bandwidth, other.bandwidth):
        if bandwidth is not None and np.isfinite(bandwidth):
            tolerance = max(tolerance, float(bandwidth))
    return abs(float(other_wl) - float(ref_wl)) <= tolerance
