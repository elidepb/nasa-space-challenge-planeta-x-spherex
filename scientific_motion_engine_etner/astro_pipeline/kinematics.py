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


def fit_parallax_and_proper_motion(detections: list[dict]) -> dict:
    """
    Ajusta simultáneamente posición base (ra0, dec0), movimiento propio lineal
    (pm_ra, pm_dec) y paralaje anual (parallax) a partir de >= 3 épocas.
    detections = [{"mjd": 61000.5, "ra": 133.78, "dec": -7.24}, ...]
    """
    import numpy as np
    from astropy.time import Time
    from astropy.coordinates import get_body_barycentric
    import astropy.units as u

    if len(detections) < 3:
        raise ValueError("Se requieren al menos 3 épocas para ajustar paralaje y movimiento propio.")

    t0 = detections[0]["mjd"]
    ra0, dec0 = np.deg2rad(detections[0]["ra"]), np.deg2rad(detections[0]["dec"])

    A_rows = []
    b_obs = []

    for det in detections:
        dt_yr = (det["mjd"] - t0) / 365.25
        # Posición baricéntrica de la Tierra en UA en la época de observación
        t_astro = Time(det["mjd"], format="mjd")
        earth_xyz = get_body_barycentric("earth", t_astro).xyz.to(u.AU).value
        X, Y, Z = earth_xyz[0], earth_xyz[1], earth_xyz[2]

        # Factores paralácticos proyectados en el plano tangente (RA, Dec)
        pi_alpha = X * np.sin(ra0) - Y * np.cos(ra0)
        pi_delta = X * np.cos(ra0) * np.sin(dec0) + Y * np.sin(ra0) * np.sin(dec0) - Z * np.cos(dec0)

        # Desplazamientos observados en arcsec respecto a t0
        dra_arcsec = (det["ra"] - detections[0]["ra"]) * np.cos(dec0) * 3600.0
        ddec_arcsec = (det["dec"] - detections[0]["dec"]) * 3600.0

        # Ecuaciones matriciales para [offset_ra, offset_dec, pm_ra, pm_dec, parallax]
        A_rows.append([1.0, 0.0, dt_yr, 0.0, pi_alpha])
        A_rows.append([0.0, 1.0, 0.0, dt_yr, pi_delta])
        b_obs.extend([dra_arcsec, ddec_arcsec])

    A = np.array(A_rows)
    b = np.array(b_obs)

    # Resolución por mínimos cuadrados (SVD)
    params, residuals, _, _ = np.linalg.lstsq(A, b, rcond=None)
    _, _, pm_ra, pm_dec, parallax_arcsec = params

    # Cálculo de residuos RMS en arcsec
    pred_b = A @ params
    residual_arcsec = float(np.sqrt(np.mean((b - pred_b) ** 2)))
    max_allowed_residual = 0.8  # arcsec tolerancia típica según resolución SPHEREx/WISE

    total_pm = float(np.hypot(pm_ra, pm_dec))
    dist_au = float(1.0 / parallax_arcsec) if parallax_arcsec > 0.05 else None

    # Determinación de régimen cinemático
    # Planeta X esperado: d in [300, 1000] AU -> parallax in [0.001, 0.0033]'', pm total < 3.5''/yr
    if total_pm < 0.2 and parallax_arcsec < 0.05:
        regime = "STATIC"
    elif total_pm > 10.0 or (dist_au is not None and dist_au < 50.0):
        regime = "FAST"
    else:
        regime = "SLOW_COHERENT"

    return {
        "pmRaMasYr": round(float(pm_ra * 1000.0), 2),
        "pmDecMasYr": round(float(pm_dec * 1000.0), 2),
        "totalMotionArcsecYr": round(total_pm, 3),
        "parallaxArcsec": round(float(max(0.0, parallax_arcsec)), 3),
        "estimatedDistanceAu": round(dist_au, 1) if dist_au else None,
        "residual_arcsec": round(residual_arcsec, 4),
        "max_allowed_residual": max_allowed_residual,
        "regime": regime,
    }


def evaluate_tracklet(tracklet_detections: list[dict]) -> dict:
    tracklet_id = tracklet_detections[0].get("tracklet_id", "unknown")
    if len(tracklet_detections) < 3:
        return {
            "tracklet_id": tracklet_id,
            "status": "INSUFFICIENT_EPOCHS",
            "score": 0.0,
            "residual_arcsec": None,
        }

    fit = fit_parallax_and_proper_motion(tracklet_detections)

    if fit["regime"] == "STATIC" or fit["residual_arcsec"] > fit["max_allowed_residual"]:
        return {
            "tracklet_id": tracklet_id,
            "status": "STATIC_OR_NOISY_FIT",
            "score": 0.0,
            "residual_arcsec": fit["residual_arcsec"],
        }

    if fit["regime"] == "FAST":
        return {
            "tracklet_id": tracklet_id,
            "status": "FAST_SOLAR_SYSTEM",
            "score": 0.15,
            "residual_arcsec": fit["residual_arcsec"],
        }

    kinematic_term = max(0.0, 1.0 - fit["residual_arcsec"] / fit["max_allowed_residual"])
    mean_snr = sum(d.get("snr_local", d.get("snr", 5.0)) for d in tracklet_detections) / len(tracklet_detections)
    snr_term = min(1.0, max(0.0, (mean_snr - 4.5) / 10.0))

    score = round(0.65 * kinematic_term + 0.35 * snr_term, 4)

    return {
        "tracklet_id": tracklet_id,
        "status": "KINEMATIC_CANDIDATE",
        "score": score,
        "residual_arcsec": fit["residual_arcsec"],
    }


