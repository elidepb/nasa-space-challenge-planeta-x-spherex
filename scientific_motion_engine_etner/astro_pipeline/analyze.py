"""Orquesta los pasos del motor sobre list[Observation] de Elide."""

from __future__ import annotations

from typing import Any

import astropy.units as u

from astro_pipeline.align import reproject_to_grid
from astro_pipeline.contracts import AnalysisResult, Observation, RejectionDiagnostics
from astro_pipeline.detect_peaks import detect_snr_peaks
from astro_pipeline.difference import snr_difference
from astro_pipeline.kinematics import candidate_from_dipole
from astro_pipeline.match_dipoles import match_moving_dipoles
from astro_pipeline.normalize import normalize_background
from astro_pipeline.read_observation import ensure_spatial_wcs, read_scientific_arrays
from astro_pipeline.subtract_zodi import subtract_zodi


def analyze_observations(
    observations: list[Observation],
    snr_threshold: float = 6.0,
    max_Step_pixels: float = 8.0,
    max_candidates: int = 25,
    min_step_pixels: float = 1.3,
    max_step_pixels: float | None = None,
) -> dict[str, Any]:
    max_step = float(max_Step_pixels if max_step_pixels is None else max_step_pixels)
    diagnostics = RejectionDiagnostics(
        snr_threshold=snr_threshold,
        min_step_pixels=min_step_pixels,
        max_step_pixels=max_step,
    )
    if len(observations) < 2:
        return AnalysisResult(candidates=[], diagnostics=diagnostics).to_dict()

    observations = [ensure_spatial_wcs(obs) for obs in observations]
    usable = [obs for obs in observations if obs.image is not None and obs.wcs() is not None]
    if len(usable) < 2:
        return AnalysisResult(candidates=[], diagnostics=diagnostics).to_dict()
    usable.sort(key=lambda obs: str(obs.timestamp))

    found = []
    diagnostics.comparable_groups = 1
    group_candidates, group_diag = _analyze_group(
        usable,
        snr_threshold=snr_threshold,
        min_step_pixels=min_step_pixels,
        max_step_pixels=max_step,
    )
    found.extend(group_candidates)
    diagnostics.merge(group_diag)

    found.sort(key=lambda cand: cand.snr, reverse=True)
    found = found[:max_candidates]
    for index, cand in enumerate(found, start=1):
        cand.id = f"C-{index:03d}"
    diagnostics.matched = len(found)
    return AnalysisResult(candidates=found, diagnostics=diagnostics).to_dict()


def _prepare_frame(observation: Observation):
    image, variance, valid, wcs, epoch = read_scientific_arrays(observation)
    image = subtract_zodi(image, observation.zodi)
    image, variance = normalize_background(image, variance, valid)
    return image, variance, wcs, epoch


def _analyze_group(
    group: list[Observation],
    *,
    snr_threshold: float,
    min_step_pixels: float,
    max_step_pixels: float,
):
    ref_obs = group[0]
    ref_image, ref_var, ref_wcs, _ref_time = _prepare_frame(ref_obs)
    frames = [(ref_obs, ref_image, ref_var, _ref_time)]

    for obs in group[1:]:
        image, variance, wcs, epoch = _prepare_frame(obs)
        image, variance = reproject_to_grid(
            image, variance, wcs, ref_wcs, ref_image.shape
        )
        frames.append((obs, image, variance, epoch))

    candidates = []
    diagnostics = RejectionDiagnostics(
        snr_threshold=snr_threshold,
        min_step_pixels=min_step_pixels,
        max_step_pixels=max_step_pixels,
    )
    for (obs_t1, img1, var1, time1), (obs_t2, img2, var2, time2) in zip(
        frames, frames[1:]
    ):
        dt_years = float((time2 - time1).to(u.year).value)
        if dt_years <= 0:
            continue
        diagnostics.epoch_pairs += 1
        snr_map, valid = snr_difference(img1, var1, img2, var2)
        peaks_pos = detect_snr_peaks(snr_map, valid, threshold=snr_threshold)
        peaks_neg = detect_snr_peaks(-snr_map, valid, threshold=snr_threshold)
        matches, pair_diag = match_moving_dipoles(
            peaks_pos,
            peaks_neg,
            img1,
            img2,
            min_step_pixels=min_step_pixels,
            max_step_pixels=max_step_pixels,
        )
        diagnostics.merge(pair_diag)
        for match in matches:
            candidates.append(
                candidate_from_dipole(
                    peak_t1=match.peak_t1,
                    peak_t2=match.peak_t2,
                    wcs=ref_wcs,
                    dt_years=dt_years,
                    obs_t1=obs_t1,
                    obs_t2=obs_t2,
                    candidate_id="pending",
                )
            )
    return candidates, diagnostics
