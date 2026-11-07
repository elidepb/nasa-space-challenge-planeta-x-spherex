"""Convierte un dipolo en píxeles a Candidate (RA/Dec, desplazamiento, μ)."""

from __future__ import annotations

from astropy.wcs import WCS

from astro_pipeline.contracts import Candidate, CandidateDetection, Observation


def candidate_from_dipole(
    *,
    peak_t1: dict[str, float],
    peak_t2: dict[str, float],
    wcs: WCS,
    dt_years: float,
    obs_t1: Observation,
    obs_t2: Observation,
    candidate_id: str,
) -> Candidate:
    coord1 = wcs.pixel_to_world(peak_t1["x"], peak_t1["y"])
    coord2 = wcs.pixel_to_world(peak_t2["x"], peak_t2["y"])
    displacement = float(coord1.separation(coord2).arcsec)
    motion = float(displacement / dt_years) if dt_years > 0 else 0.0
    detections = [
        CandidateDetection(
            observationId=obs_t1.id,
            timestamp=obs_t1.timestamp,
            ra=round(float(coord1.ra.deg), 6),
            dec=round(float(coord1.dec.deg), 6),
            x=float(peak_t1["x"]),
            y=float(peak_t1["y"]),
            snr=round(float(peak_t1["snr"]), 2),
        ),
        CandidateDetection(
            observationId=obs_t2.id,
            timestamp=obs_t2.timestamp,
            ra=round(float(coord2.ra.deg), 6),
            dec=round(float(coord2.dec.deg), 6),
            x=float(peak_t2["x"]),
            y=float(peak_t2["y"]),
            snr=round(float(peak_t2["snr"]), 2),
        ),
    ]
    return Candidate(
        id=candidate_id,
        ra=round(float(coord2.ra.deg), 6),
        dec=round(float(coord2.dec.deg), 6),
        displacementArcsec=round(displacement, 4),
        motionArcsecPerYear=round(motion, 4),
        snr=round(float(peak_t2["snr"]), 2),
        detections=detections,
        status="candidate",
    )
