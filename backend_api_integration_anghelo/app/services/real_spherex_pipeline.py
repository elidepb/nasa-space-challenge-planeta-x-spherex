from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits
from astropy.stats import SigmaClip
from astropy.wcs import WCS
from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture
from photutils.detection import DAOStarFinder


@dataclass
class SedMeasurement:
    wavelengths_um: list[float]
    flux: list[float]
    flux_err: list[float]
    mask_flags: list[int]
    ch4_band_depth: Optional[float]
    ch4_band_snr: Optional[float]


def _compute_ch4_metrics(
    wavelengths: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    mask_flags: np.ndarray,
) -> tuple[Optional[float], Optional[float]]:
    band_mask = (wavelengths >= 3.15) & (wavelengths <= 3.45)
    cont_mask = ((wavelengths >= 2.85) & (wavelengths <= 3.10)) | (
        (wavelengths >= 3.50) & (wavelengths <= 3.85)
    )

    if not np.any(band_mask) or not np.any(cont_mask):
        return None, None

    invalid_band_ratio = float(np.mean(mask_flags[band_mask] != 0))
    if invalid_band_ratio > 0.30:
        return None, None

    valid_cont = cont_mask & (mask_flags == 0) & np.isfinite(flux) & (flux_err > 0)
    valid_band = band_mask & (mask_flags == 0) & np.isfinite(flux) & (flux_err > 0)
    if np.count_nonzero(valid_cont) < 2 or np.count_nonzero(valid_band) == 0:
        return None, None

    weights = 1.0 / (flux_err[valid_cont] ** 2)
    poly_coeffs = np.polyfit(wavelengths[valid_cont], flux[valid_cont], deg=1, w=weights)
    continuum_band = np.polyval(poly_coeffs, wavelengths[valid_band])

    observed_band = flux[valid_band]
    err_band = flux_err[valid_band]

    mean_cont = float(np.mean(continuum_band))
    mean_obs = float(np.mean(observed_band))
    if mean_cont <= 0:
        return None, None

    ch4_depth = float(np.clip(1.0 - (mean_obs / mean_cont), 0.0, 1.0))
    inv_var = 1.0 / (err_band ** 2)
    ch4_snr = float(
        np.sum((continuum_band - observed_band) * inv_var) / np.sqrt(np.sum(inv_var))
    )
    return ch4_depth, ch4_snr


def extract_real_candidates_from_fits(
    fits_path: Path,
    ra_deg: float,
    dec_deg: float,
    radius_arcmin: float = 5.0,
    snr_threshold: float = 5.0,
    fwhm_px: float = 2.5,
) -> dict:
    with fits.open(fits_path) as hdul:
        sci_hdu = hdul["SCI"] if "SCI" in hdul else hdul[0]
        err_hdu = hdul["ERR"] if "ERR" in hdul else (hdul["VAR"] if "VAR" in hdul else None)
        dq_hdu = hdul["DQ"] if "DQ" in hdul else None

        header = sci_hdu.header
        wcs = WCS(header)
        if not wcs.has_celestial:
            raise ValueError(f"El archivo {fits_path.name} no contiene WCS celestial válido.")

        sci_cube = np.asarray(sci_hdu.data, dtype=np.float64)
        if err_hdu is not None:
            err_cube = np.asarray(err_hdu.data, dtype=np.float64)
            if "VAR" in hdul and "ERR" not in hdul:
                err_cube = np.sqrt(np.clip(err_cube, 0.0, np.inf))
        else:
            err_cube = np.ones_like(sci_cube, dtype=np.float64)

        n_chan, ny, nx = sci_cube.shape
        dq_cube = (
            np.asarray(dq_hdu.data, dtype=np.int32)
            if dq_hdu is not None
            else np.zeros((n_chan, ny, nx), dtype=np.int32)
        )

        # Longitudes de onda desde tabla WAVELENGTH o palabras clave CDELT3/CRVAL3
        if "WAVELENGTH" in hdul:
            wavelengths = np.asarray(hdul["WAVELENGTH"].data, dtype=np.float64).ravel()
        else:
            crval3 = float(header.get("CRVAL3", 0.75))
            cdelt3 = float(header.get("CDELT3", 0.04))
            wavelengths = crval3 + cdelt3 * np.arange(n_chan, dtype=np.float64)

        x0, y0 = wcs.world_to_pixel_values(ra_deg, dec_deg)
        if not (0.0 <= x0 < nx and 0.0 <= y0 < ny):
            return {
                "status": "no_spherex_coverage",
                "statusDetail": f"Coordenadas ({ra_deg}, {dec_deg}) fuera del rango de píxeles {nx}x{ny}.",
                "candidates": [],
            }

        half_win = max(16, int(np.ceil((radius_arcmin * 60.0) / 6.2)))
        x_min = max(0, int(np.floor(x0)) - half_win)
        x_max = min(nx, int(np.ceil(x0)) + half_win + 1)
        y_min = max(0, int(np.floor(y0)) - half_win)
        y_max = min(ny, int(np.ceil(y0)) + half_win + 1)

        sub_sci = sci_cube[:, y_min:y_max, x_min:x_max]
        sub_err = err_cube[:, y_min:y_max, x_min:x_max]
        sub_dq = dq_cube[:, y_min:y_max, x_min:x_max]

        invalid_pix = (sub_dq != 0) | (~np.isfinite(sub_sci)) | (~np.isfinite(sub_err)) | (sub_err <= 0)
        safe_err = np.where(invalid_pix, np.inf, sub_err)
        weights = np.where(np.isfinite(safe_err), 1.0 / (safe_err ** 2), 0.0)
        weight_sum = np.sum(weights, axis=0)

        det_image = np.where(
            weight_sum > 0,
            np.sum(weights * np.where(invalid_pix, 0.0, sub_sci), axis=0) / np.where(weight_sum > 0, weight_sum, 1.0),
            np.nan,
        )

        sigma_clip = SigmaClip(sigma=3.0, maxiters=5)
        valid_det = np.isfinite(det_image)
        _, det_median, det_std = sigma_clip(det_image[valid_det], masked=False, return_bounds=False)
        det_sub = det_image - det_median

        finder = DAOStarFinder(fwhm=fwhm_px, threshold=snr_threshold * float(det_std))
        sources = finder(det_sub)

        candidates = []
        if sources is not None:
            for idx, row in enumerate(sources):
                cx = float(row["xcentroid"]) + x_min
                cy = float(row["ycentroid"]) + y_min
                c_ra, c_dec = wcs.pixel_to_world_values(cx, cy)

                ap = CircularAperture((cx, cy), r=2.0)
                ann = CircularAnnulus((cx, cy), r_in=4.5, r_out=7.0)
                n_ap = ap.area

                flux_list = []
                err_list = []
                mask_list = []

                for k in range(n_chan):
                    plane_sci = sci_cube[k]
                    plane_err = err_cube[k]
                    plane_dq = dq_cube[k]

                    ap_mask = ap.to_mask(method="center")
                    ap_dq_vals = ap_mask.multiply(plane_dq, fill_value=1)
                    if ap_dq_vals is None or np.any(ap_dq_vals != 0):
                        flux_list.append(float("nan"))
                        err_list.append(float("inf"))
                        mask_list.append(1)
                        continue

                    ann_stats = ApertureStats(plane_sci, ann, sigma_clip=sigma_clip)
                    bg_mean = float(ann_stats.mean)
                    bg_std = float(ann_stats.std)
                    n_bg = max(1.0, float(ann_stats.sum_aper_area.value))

                    ap_sum = float(np.sum(ap_mask.multiply(plane_sci)))
                    err_sq_sum = float(np.sum(ap_mask.multiply(plane_err ** 2)))

                    net_flux = ap_sum - (n_ap * bg_mean)
                    net_err = float(
                        np.sqrt(err_sq_sum + n_ap * (bg_std ** 2) * (1.0 + (n_ap / n_bg)))
                    )

                    flux_list.append(net_flux)
                    err_list.append(net_err)
                    mask_list.append(0)

                flux_arr = np.asarray(flux_list, dtype=np.float64)
                err_arr = np.asarray(err_list, dtype=np.float64)
                mask_arr = np.asarray(mask_list, dtype=np.int32)

                ch4_depth, ch4_snr = _compute_ch4_metrics(wavelengths, flux_arr, err_arr, mask_arr)
                valid_snr_mask = (mask_arr == 0) & (err_arr > 0) & np.isfinite(flux_arr)
                overall_snr = (
                    float(np.sqrt(np.sum((flux_arr[valid_snr_mask] / err_arr[valid_snr_mask]) ** 2)))
                    if np.any(valid_snr_mask)
                    else 0.0
                )

                candidates.append(
                    {
                        "detectionId": f"{header.get('OBSID', fits_path.stem)}-{idx + 1:03d}",
                        "raDeg": float(c_ra),
                        "decDeg": float(c_dec),
                        "pixelXy": [cx, cy],
                        "snr": overall_snr,
                        "properMotionMasYr": None,
                        "sed": {
                            "wavelengthsUm": wavelengths.tolist(),
                            "flux": [0.0 if not np.isfinite(v) else float(v) for v in flux_arr],
                            "fluxErr": [0.0 if not np.isfinite(v) else float(v) for v in err_arr],
                            "maskFlags": mask_arr.tolist(),
                            "ch4BandDepth": ch4_depth,
                            "ch4BandSnr": ch4_snr,
                        },
                    }
                )

        return {
            "status": "ok_real_data",
            "sourceProvenance": {
                "fitsFile": fits_path.name,
                "obsId": str(header.get("OBSID", fits_path.stem)),
                "dateObsUtc": str(header.get("DATE-OBS", "")),
                "wcsValid": True,
                "calibrationVersion": str(header.get("CALVER", "unknown")),
            },
            "candidates": candidates,
        }
