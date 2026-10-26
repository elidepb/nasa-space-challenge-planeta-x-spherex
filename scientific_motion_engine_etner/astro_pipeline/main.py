import os
import json
import warnings
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from astropy.utils.exceptions import AstropyWarning
from astropy.coordinates import SkyCoord
import astropy.units as u
from reproject import reproject_interp

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

warnings.simplefilter('ignore', category=AstropyWarning)


# =========================================================
# 1. CONTRATOS DE DATOS (Entrada / Salida)
# =========================================================

@dataclass
class Observation:
    data: np.ndarray        # Matriz científica 2D (MJy/sr)
    variance: np.ndarray    # Matriz de varianza 2D ((MJy/sr)^2)
    mask: np.ndarray        # Máscara booleana (True = píxel malo / ignorar)
    wcs: WCS                # Objeto Astropy WCS 2D
    epoch: Time             # Objeto Astropy Time


@dataclass
class Candidate:
    id: str
    ra: float
    dec: float
    displacementArcsec: float
    motionArcsecPerYear: float
    snr: float


@dataclass
class AnalysisResult:
    candidates: List[Candidate]

    def to_dict(self) -> Dict[str, Any]:
        return {"candidates": [asdict(c) for c in self.candidates]}


# =========================================================
# 2. LECTOR ARCHIVOS FITS DE SPHEREx
# =========================================================

def load_spherex_observation(
    fits_path: str,
    subtract_zodi: bool = True,
    bitmask_ignore: int = 0
) -> Observation:
    """
    Lee un archivo FITS de SPHEREx y enmascara automáticamente bloques truncados (ceros).
    """
    with fits.open(fits_path, ignore_missing_end=True) as hdul:
        ext_names = [h.name for h in hdul]

        img_hdu = None
        for candidate_ext in ('IMAGE', 'SCI', 'PRIMARY'):
            if candidate_ext in ext_names and hdul[candidate_ext].data is not None:
                img_hdu = hdul[candidate_ext]
                break
        if img_hdu is None:
            for h in hdul:
                if h.data is not None and h.data.ndim >= 2:
                    img_hdu = h
                    break
        if img_hdu is None:
            raise ValueError(f"No se encontró ninguna matriz 2D en {fits_path}")

        data = np.array(img_hdu.data, dtype=float, copy=True)
        header = img_hdu.header

        # Detectar píxeles truncados en disco (exactamente 0.0 en bloques FITS incompletos)
        truncated_mask = (data == 0.0) | ~np.isfinite(data)

        if subtract_zodi and 'ZODI' in ext_names and hdul['ZODI'].data is not None:
            try:
                zodi = np.array(hdul['ZODI'].data, dtype=float)
                if zodi.shape == data.shape:
                    data = data - zodi
            except Exception:
                pass

        variance = None
        for var_ext in ('VARIANCE', 'VAR', 'UNCERTAINTY', 'ERR'):
            if var_ext in ext_names:
                try:
                    raw_var = hdul[var_ext].data
                    if raw_var is not None and raw_var.shape == data.shape:
                        variance = np.array(raw_var, dtype=float, copy=True)
                        if var_ext in ('UNCERTAINTY', 'ERR'):
                            variance = variance ** 2
                        break
                except Exception:
                    variance = None

        # Fallback: estimar varianza solo sobre píxeles válidos (no truncados)
        if variance is None:
            valid_pixels = data[~truncated_mask]
            if len(valid_pixels) > 0:
                med = np.median(valid_pixels)
                sigma_est = 1.4826 * np.median(np.abs(valid_pixels - med))
                var_val = (sigma_est ** 2) if sigma_est > 0 else 1.0
            else:
                var_val = 1.0
            variance = np.full_like(data, var_val, dtype=float)

        mask = None
        for mask_ext in ('FLAGS', 'MASK', 'DQ'):
            if mask_ext in ext_names:
                try:
                    raw_flags = hdul[mask_ext].data
                    if raw_flags is not None and raw_flags.shape == data.shape:
                        flags = np.array(raw_flags, dtype=int)
                        mask = (flags & (~bitmask_ignore)) > 0
                        break
                except Exception:
                    mask = None

        if mask is None:
            mask = np.zeros_like(data, dtype=bool)

        mask = mask | truncated_mask | ~np.isfinite(variance) | (variance <= 0)
        wcs = WCS(header, naxis=2)

        hdr_to_check = [header, hdul[0].header]
        epoch = None
        for h in hdr_to_check:
            for key, fmt in (('MJD-AVG', 'mjd'), ('MJD-OBS', 'mjd'), ('MJD', 'mjd'),
                             ('DATE-AVG', 'isot'), ('DATE-OBS', 'isot'), ('DATE', 'isot')):
                if key in h and h[key]:
                    try:
                        epoch = Time(h[key], format=fmt)
                        break
                    except Exception:
                        continue
            if epoch is not None:
                break

        if epoch is None:
            epoch = Time(60800.0, format='mjd')

    return Observation(
        data=data,
        variance=variance,
        mask=mask,
        wcs=wcs,
        epoch=epoch
    )


# =========================================================
# 3. FUNCIONES AUXILIARES
# =========================================================

def smooth_gaussian_np(img: np.ndarray, sigma: float = 0.8) -> np.ndarray:
    """Filtro gaussiano 2D separable en NumPy puro."""
    radius = max(1, int(round(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=float)
    kernel_1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel_1d /= np.sum(kernel_1d)

    clean = np.nan_to_num(img, nan=0.0)
    temp = np.apply_along_axis(lambda m: np.convolve(m, kernel_1d, mode='same'), axis=1, arr=clean)
    return np.apply_along_axis(lambda m: np.convolve(m, kernel_1d, mode='same'), axis=0, arr=temp)


def detect_snr_peaks(snr_image: np.ndarray, valid_mask: np.ndarray, threshold: float = 6.0) -> List[Dict[str, float]]:
    """
    Detecta máximos locales significativos sobre el mapa de SNR, ignorando bordes
    de píxeles enmascarados o zonas truncadas.
    """
    clean_snr = np.nan_to_num(snr_image, nan=0.0)
    ny, nx = clean_snr.shape

    ys, xs = np.where((clean_snr >= threshold) & valid_mask)
    sources = []

    for y, x in zip(ys, xs):
        if y < 6 or y >= ny - 6 or x < 6 or x >= nx - 6:
            continue

        # Si hay algún píxel inválido/truncado en la vecindad 5x5, descartar (evita artefactos de borde/máscara)
        if not np.all(valid_mask[y - 2:y + 3, x - 2:x + 3]):
            continue

        val = clean_snr[y, x]
        patch_5x5 = clean_snr[y - 2:y + 3, x - 2:x + 3]
        if val < np.max(patch_5x5):
            continue

        if np.sum(patch_5x5 == val) > 1:
            max_y, max_x = np.argwhere(patch_5x5 == val)[0]
            if (max_y != 2) or (max_x != 2):
                continue

        # Centroide sub-píxel en ventana 3x3
        patch_3x3 = np.maximum(clean_snr[y - 1:y + 2, x - 1:x + 2], 0.0)
        total_w = np.sum(patch_3x3)
        if total_w <= 0:
            continue

        gy, gx = np.mgrid[y - 1:y + 2, x - 1:x + 2]
        x_cen = float(np.sum(gx * patch_3x3) / total_w)
        y_cen = float(np.sum(gy * patch_3x3) / total_w)

        sources.append({
            "x": x_cen,
            "y": y_cen,
            "snr": float(val)
        })

    return sources


def preprocess_and_normalize(obs: Observation) -> Tuple[np.ndarray, np.ndarray]:
    """Tareas 2, 3 y 6: Aplica máscara de calidad y normaliza fondo e intensidad."""
    data = np.array(obs.data, dtype=float, copy=True)
    var = np.array(obs.variance, dtype=float, copy=True)

    if obs.mask is not None:
        bad = obs.mask.astype(bool)
        data[bad] = np.nan
        var[bad] = np.nan

    bkg = np.nanmedian(data)
    mad = np.nanmedian(np.abs(data - bkg))
    scale = (1.4826 * mad) if mad > 0 else 1.0

    norm_data = (data - bkg) / scale
    norm_var = var / (scale ** 2)

    return norm_data, norm_var


def align_observation(data, var, wcs_in, wcs_ref, shape_ref) -> Tuple[np.ndarray, np.ndarray]:
    """Tareas 4 y 5: Alinea observaciones usando WCS y reproyecta a cuadrícula común."""
    if wcs_in.to_header_string() == wcs_ref.to_header_string() and data.shape == shape_ref:
        return data, var

    aligned_data, footprint = reproject_interp((data, wcs_in), wcs_ref, shape_out=shape_ref)
    aligned_var, _ = reproject_interp((var, wcs_in), wcs_ref, shape_out=shape_ref)

    out_of_bounds = (footprint < 0.99) | ~np.isfinite(aligned_data) | ~np.isfinite(aligned_var)
    aligned_data[out_of_bounds] = np.nan
    aligned_var[out_of_bounds] = np.nan

    return aligned_data, aligned_var


# =========================================================
# 4. INTERFAZ PRINCIPAL ESPERADA
# =========================================================

def analyze_observations(
    observations: List[Observation],
    snr_threshold: float = 6.0,
    max_Step_pixels: float = 8.0,
    max_candidates: int = 25
) -> Dict[str, Any]:
    """
    Ejecuta el pipeline de detección de movimiento con emparejamiento 1-a-1
    y veto de residuos de estrellas estáticas.
    """
    if len(observations) < 2:
        return AnalysisResult(candidates=[]).to_dict()

    obs_sorted = sorted(observations, key=lambda x: x.epoch.jd)
    for idx in range(1, len(obs_sorted)):
        if obs_sorted[idx].epoch.jd <= obs_sorted[idx - 1].epoch.jd:
            obs_sorted[idx].epoch = obs_sorted[idx - 1].epoch + 182.625 * u.day

    ref_wcs = obs_sorted[0].wcs
    ref_shape = obs_sorted[0].data.shape

    aligned_epochs = []
    for obs in obs_sorted:
        norm_d, norm_v = preprocess_and_normalize(obs)
        al_d, al_v = align_observation(norm_d, norm_v, obs.wcs, ref_wcs, ref_shape)
        aligned_epochs.append((al_d, al_v, obs.epoch))

    raw_candidates = []

    for i in range(len(aligned_epochs) - 1):
        d1, v1, t1 = aligned_epochs[i]
        d2, v2, t2 = aligned_epochs[i + 1]

        dt_years = float((t2 - t1).to(u.year).value)
        if dt_years <= 0:
            continue

        # Tarea 8 y 9: Image differencing y SNR con VARIANCE
        diff = d2 - d1
        var_diff = v1 + v2
        noise = np.sqrt(var_diff)

        valid = np.isfinite(diff) & np.isfinite(noise) & (noise > 0)
        snr_map = np.zeros_like(diff)
        snr_map[valid] = diff[valid] / noise[valid]

        # Tarea 10: Detectar picos positivos (t2) y negativos (t1)
        sources_pos = detect_snr_peaks(snr_map, valid, threshold=snr_threshold)
        sources_neg = detect_snr_peaks(-snr_map, valid, threshold=snr_threshold)

        if not sources_pos or not sources_neg:
            continue

        # Tarea 11 y 13: Emparejamiento mutuo 1-a-1 (evita que múltiples picos usen el mismo hueco)
        possible_pairs = []
        for p_idx, pos in enumerate(sources_pos):
            for n_idx, neg in enumerate(sources_neg):
                dist_pix = float(np.hypot(pos["x"] - neg["x"], pos["y"] - neg["y"]))
                flux_ratio = pos["snr"] / neg["snr"]

                # Rango físico: entre 1.3 px (evita dipolos de mal alineamiento de estrellas fijas)
                # y max_Step_pixels (8 px ~= 49" en SPHEREx) con flujo consistente
                if 1.3 <= dist_pix <= max_Step_pixels and (0.6 <= flux_ratio <= 1.67):
                    possible_pairs.append((dist_pix, p_idx, n_idx))

        # Ordenar pares por menor distancia para asignación exclusiva 1-a-1
        possible_pairs.sort(key=lambda item: item[0])
        used_pos = set()
        used_neg = set()

        for dist_pix, p_idx, n_idx in possible_pairs:
            if p_idx in used_pos or n_idx in used_neg:
                continue

            pos = sources_pos[p_idx]
            neg = sources_neg[n_idx]

            # Filtro anti-estrella fija: en t2 la posición (x1, y1) debe haber quedado vacía (fondo)
            # y en t1 la posición (x2, y2) debía estar vacía
            ix1, iy1 = int(round(neg["x"])), int(round(neg["y"]))
            ix2, iy2 = int(round(pos["x"])), int(round(pos["y"]))
            if d2[iy1, ix1] > 4.0 or d1[iy2, ix2] > 4.0:
                continue

            used_pos.add(p_idx)
            used_neg.add(n_idx)

            coord1 = ref_wcs.pixel_to_world(neg["x"], neg["y"])
            coord2 = ref_wcs.pixel_to_world(pos["x"], pos["y"])

            displacement_arcsec = float(coord1.separation(coord2).arcsec)
            motion_arcsec_yr = float(displacement_arcsec / dt_years)

            raw_candidates.append({
                "ra": round(float(coord2.ra.deg), 6),
                "dec": round(float(coord2.dec.deg), 6),
                "displacementArcsec": round(displacement_arcsec, 4),
                "motionArcsecPerYear": round(motion_arcsec_yr, 4),
                "snr": round(float(pos["snr"]), 2)
            })

    # Ordenar de mayor a menor SNR y limitar a los mejores candidatos
    raw_candidates.sort(key=lambda c: c["snr"], reverse=True)
    raw_candidates = raw_candidates[:max_candidates]

    final_candidates = [
        Candidate(
            id=f"C-{idx:03d}",
            ra=c["ra"],
            dec=c["dec"],
            displacementArcsec=c["displacementArcsec"],
            motionArcsecPerYear=c["motionArcsecPerYear"],
            snr=c["snr"]
        )
        for idx, c in enumerate(raw_candidates, start=1)
    ]

    return AnalysisResult(candidates=final_candidates).to_dict()


# =========================================================
# 5. GENERADOR DE FITS SINTÉTICOS SPHEREx Y EJECUCIÓN
# =========================================================

def create_mock_spherex_fits(
    filename: str,
    mjd: float,
    obj_xy: tuple,
    shift_wcs_px: tuple = (0.0, 0.0)
):
    shape = (120, 120)
    np.random.seed(int(mjd))

    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [60.0 + shift_wcs_px[0], 60.0 + shift_wcs_px[1]]
    scale_deg = 6.15 / 3600.0
    wcs.wcs.cdelt = [-scale_deg, scale_deg]
    wcs.wcs.crval = [150.0, 2.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = wcs.to_header()
    header['MJD-AVG'] = mjd

    zodi = np.full(shape, 50.0, dtype=np.float32)
    noise_sigma = 2.0
    sky_noise = np.random.normal(0.0, noise_sigma, shape)

    static_star = np.zeros(shape)
    static_star[60 - int(shift_wcs_px[1]), 60 - int(shift_wcs_px[0])] = 400.0
    static_star = smooth_gaussian_np(static_star, sigma=0.8)

    moving_obj = np.zeros(shape)
    ox, oy = obj_xy[0] - int(shift_wcs_px[0]), obj_xy[1] - int(shift_wcs_px[1])
    moving_obj[oy, ox] = 350.0
    moving_obj = smooth_gaussian_np(moving_obj, sigma=0.8)

    image_data = (zodi + static_star + moving_obj + sky_noise).astype(np.float32)
    variance_data = np.full(shape, noise_sigma ** 2, dtype=np.float32)
    flags_data = np.zeros(shape, dtype=np.int32)

    flags_data[10, 10] = 2
    image_data[10, 10] = 99999.0

    hdul = fits.HDUList([
        fits.PrimaryHDU(header=header),
        fits.ImageHDU(data=image_data, header=header, name='IMAGE'),
        fits.ImageHDU(data=variance_data, header=header, name='VARIANCE'),
        fits.ImageHDU(data=flags_data, header=header, name='FLAGS'),
        fits.ImageHDU(data=zodi, header=header, name='ZODI')
    ])
    hdul.writeto(filename, overwrite=True)



# =========================================================
# 6. VISUALIZACIÓN PROFESIONAL DE CANDIDATOS
# =========================================================

def _asinh_stretch(img: np.ndarray, q: float = 0.01) -> np.ndarray:
    """Aplica un stretch arcsinh para resaltar fuentes tenues sin saturar las brillantes."""
    valid = img[np.isfinite(img)]
    if len(valid) == 0:
        return np.zeros_like(img)
    vmin = np.percentile(valid, q * 100)
    vmax = np.percentile(valid, (1 - q) * 100)
    clipped = np.clip(img, vmin, vmax)
    normalized = (clipped - vmin) / max(vmax - vmin, 1e-10)
    # asinh stretch con factor de escala
    a = 0.1
    stretched = np.arcsinh(normalized / a) / np.arcsinh(1.0 / a)
    return np.nan_to_num(stretched, nan=0.0)


def visualize_candidates_on_image(
    observation: Observation,
    candidates: List[Dict[str, Any]],
    output_path: str = "candidates_marked.png",
    box_half_size: int = 8,
    show_plot: bool = True
) -> str:
    """
    Genera una visualización de calidad profesional con:
    - Panel principal: campo completo con candidatos marcados (cuadros rojos + crucetas)
    - Paneles de zoom: cutout ampliado de cada candidato
    - Stretch asinh para revelar fuentes tenues
    - Colormap infrarrojo (hot) sobre fondo oscuro

    Parámetros
    ----------
    observation : Observation
        La observación de referencia cuya imagen se usa como fondo.
    candidates : list[dict]
        Lista de candidatos con al menos las claves 'ra', 'dec', 'id' y 'snr'.
    output_path : str
        Ruta donde guardar la imagen PNG resultante.
    box_half_size : int
        Mitad del lado del cuadro rojo en píxeles.
    show_plot : bool
        Si True, muestra la ventana interactiva de matplotlib.

    Retorna
    -------
    str
        Ruta absoluta al archivo PNG guardado.
    """
    if not show_plot:
        matplotlib.use('Agg')

    from matplotlib.patches import FancyBboxPatch
    from matplotlib.gridspec import GridSpec
    from matplotlib.colors import LinearSegmentedColormap

    # --- Preparar la imagen de fondo ---
    img_raw = np.array(observation.data, dtype=float, copy=True)
    if observation.mask is not None:
        img_raw[observation.mask.astype(bool)] = np.nan

    # Suavizado ligero para reducir ruido visual (no altera datos científicos)
    img_smooth = smooth_gaussian_np(np.nan_to_num(img_raw, nan=np.nanmedian(img_raw)), sigma=0.6)

    # Stretch asinh para presentación
    img_display = _asinh_stretch(img_smooth, q=0.005)

    # --- Colormap infrarrojo personalizado ---
    colors_custom = [
        (0.00, '#050510'),  # negro profundo
        (0.10, '#0a0a2e'),  # azul oscurísimo
        (0.25, '#1a0a3a'),  # púrpura profundo
        (0.40, '#3d0c5c'),  # magenta oscuro
        (0.55, '#8b1a4a'),  # rojo-magenta
        (0.70, '#c44e2b'),  # naranja
        (0.82, '#e8a020'),  # amarillo-naranja
        (0.92, '#f5dc58'),  # amarillo brillante
        (1.00, '#fffff0'),  # blanco cálido
    ]
    cmap_astro = LinearSegmentedColormap.from_list(
        'spherex_infrared',
        [(pos, color) for pos, color in colors_custom],
        N=512
    )

    # --- Resolver posiciones de píxel de los candidatos ---
    cand_pixels = []
    for cand in candidates:
        ra = cand.get("ra")
        dec = cand.get("dec")
        if ra is None or dec is None:
            continue
        sky = SkyCoord(ra=ra, dec=dec, unit='deg')
        try:
            px, py = observation.wcs.world_to_pixel(sky)
            px, py = float(px), float(py)
        except Exception:
            continue
        ny, nx = img_display.shape
        if 0 <= px < nx and 0 <= py < ny:
            cand_pixels.append({**cand, '_px': px, '_py': py})

    n_cands = len(cand_pixels)
    n_zoom = min(n_cands, 6)  # Máximo 6 paneles de zoom

    # --- Layout: panel principal + paneles de zoom a la derecha ---
    if n_zoom > 0:
        fig = plt.figure(figsize=(16, 10), facecolor='#08090d')
        gs = GridSpec(max(n_zoom, 2), 4, figure=fig, wspace=0.35, hspace=0.4)
        ax_main = fig.add_subplot(gs[:, :3], projection=observation.wcs)
    else:
        fig, ax_main = plt.subplots(1, 1, figsize=(12, 10), subplot_kw={'projection': observation.wcs})
        fig.patch.set_facecolor('#08090d')

    # --- Panel principal ---
    im = ax_main.imshow(
        img_display, origin='lower', cmap=cmap_astro,
        vmin=0, vmax=1, interpolation='bicubic', aspect='equal'
    )

    # Estilo de ejes WCS
    ax_main.set_facecolor('#050510')
    ax_main.coords[0].set_axislabel('Right Ascension (J2000)', fontsize=11, color='#cccccc')
    ax_main.coords[1].set_axislabel('Declination (J2000)', fontsize=11, color='#cccccc')
    ax_main.coords[0].set_ticklabel(color='#999999', size=9)
    ax_main.coords[1].set_ticklabel(color='#999999', size=9)
    ax_main.coords.grid(color='#ffffff', alpha=0.08, linestyle='-', linewidth=0.5)
    ax_main.tick_params(axis='both', colors='#666666')

    # Título principal
    ax_main.set_title(
        'SPHEREx — Moving Object Candidate Detection',
        fontsize=15, fontweight='bold', color='#e8e8f0',
        pad=15, fontfamily='monospace'
    )

    # --- Marcar cada candidato ---
    marker_colors = ['#ff2d2d', '#ff6b35', '#ffd23f', '#3bceac', '#0ead69', '#6c5ce7']
    n_marked = 0

    for idx, cand in enumerate(cand_pixels):
        px, py = cand['_px'], cand['_py']
        cand_id = cand.get("id", f"C-{idx+1:03d}")
        snr = cand.get("snr", 0.0)
        motion = cand.get("motionArcsecPerYear", 0.0)
        color = marker_colors[idx % len(marker_colors)]

        # ── Cuadro rojo con esquinas redondeadas ──
        rect = FancyBboxPatch(
            (px - box_half_size, py - box_half_size),
            2 * box_half_size, 2 * box_half_size,
            boxstyle="round,pad=1",
            linewidth=2.0, edgecolor=color, facecolor='none',
            linestyle='-', zorder=10
        )
        ax_main.add_patch(rect)

        # ── Cruceta central ──
        cross_len = box_half_size * 0.4
        ax_main.plot([px - cross_len, px + cross_len], [py, py],
                     color=color, linewidth=1.2, alpha=0.9, zorder=11)
        ax_main.plot([px, px], [py - cross_len, py + cross_len],
                     color=color, linewidth=1.2, alpha=0.9, zorder=11)

        # ── Etiqueta ──
        label_y_offset = box_half_size + 3
        ax_main.annotate(
            f"{cand_id}",
            xy=(px, py + label_y_offset),
            fontsize=7.5, color=color, fontweight='bold',
            ha='center', va='bottom', zorder=12,
            bbox=dict(
                boxstyle='round,pad=0.25',
                facecolor='#0a0a0a', alpha=0.85,
                edgecolor=color, linewidth=0.8
            )
        )

        n_marked += 1

    # --- Info box superior izquierda ---
    info_text = (
        f"Candidatos detectados: {n_marked}\n"
        f"Época: {observation.epoch.iso[:10]}\n"
        f"Campo: {img_raw.shape[1]}×{img_raw.shape[0]} px"
    )
    ax_main.text(
        0.015, 0.985, info_text,
        transform=ax_main.transAxes,
        fontsize=9, color='#ff6666', fontfamily='monospace',
        fontweight='bold', verticalalignment='top',
        bbox=dict(
            boxstyle='round,pad=0.5',
            facecolor='#0a0a0a', alpha=0.9,
            edgecolor='#ff4444', linewidth=1.2
        ), zorder=20
    )

    # --- Paneles de zoom (cutouts ampliados) ---
    cutout_radius = 15  # píxeles alrededor del candidato

    for idx in range(n_zoom):
        cand = cand_pixels[idx]
        px, py = int(round(cand['_px'])), int(round(cand['_py']))
        cand_id = cand.get("id", f"C-{idx+1:03d}")
        snr = cand.get("snr", 0.0)
        motion = cand.get("motionArcsecPerYear", 0.0)
        displacement = cand.get("displacementArcsec", 0.0)
        color = marker_colors[idx % len(marker_colors)]

        # Extraer cutout
        ny, nx = img_display.shape
        y0 = max(0, py - cutout_radius)
        y1 = min(ny, py + cutout_radius + 1)
        x0 = max(0, px - cutout_radius)
        x1 = min(nx, px + cutout_radius + 1)
        cutout = img_display[y0:y1, x0:x1]

        ax_zoom = fig.add_subplot(gs[idx, 3])
        ax_zoom.imshow(
            cutout, origin='lower', cmap=cmap_astro,
            vmin=0, vmax=1, interpolation='bicubic', aspect='equal'
        )

        # Cruceta en el centro del cutout
        cy, cx = cutout.shape[0] / 2, cutout.shape[1] / 2
        cl = 2.5
        ax_zoom.plot([cx - cl, cx + cl], [cy, cy], color=color, lw=1.5, alpha=0.9)
        ax_zoom.plot([cx, cx], [cy - cl, cy + cl], color=color, lw=1.5, alpha=0.9)

        # Borde coloreado
        for spine in ax_zoom.spines.values():
            spine.set_edgecolor(color)
            spine.set_linewidth(2)

        ax_zoom.set_xticks([])
        ax_zoom.set_yticks([])
        ax_zoom.set_facecolor('#050510')

        # Info del candidato
        zoom_label = f"{cand_id}  SNR={snr:.1f}\n{motion:.2f}\"/yr  Δ={displacement:.2f}\""
        ax_zoom.set_title(
            zoom_label, fontsize=7.5, color=color,
            fontweight='bold', fontfamily='monospace', pad=4
        )

    # --- Colorbar ---
    cbar_ax = fig.add_axes([0.03, 0.02, 0.20, 0.015])
    cbar = fig.colorbar(im, cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Intensidad relativa (asinh stretch)', fontsize=8, color='#999999')
    cbar.ax.tick_params(labelsize=7, colors='#777777')
    cbar.outline.set_edgecolor('#333333')

    # --- Sello del pipeline ---
    fig.text(
        0.98, 0.01,
        'SPHEREx Pipeline · Planeta X · NASA Space Apps 2026',
        fontsize=7, color='#555555', ha='right', va='bottom',
        fontfamily='monospace', style='italic'
    )

    abs_path = os.path.abspath(output_path)
    fig.savefig(abs_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"\n[OK] Imagen guardada en: {abs_path}")
    print(f"    >> {n_marked} candidatos marcados")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return abs_path


if __name__ == "__main__":
    from pathlib import Path

    # Ruta exacta a tu carpeta 'spherex_6_bandas' al lado de 'astro_pipeline'
    carpeta_bandas = Path(__file__).resolve().parent.parent / "spherex_6_bandas"

    # Toma cualquier archivo dentro de spherex_6_bandas (tenga extensión .fits o similar)
    archivos = sorted([
        str(f) for f in carpeta_bandas.iterdir()
        if f.is_file() and "level2_" in f.name
    ])

    print(f"Archivos encontrados en {carpeta_bandas.name}: {len(archivos)}")
    for a in archivos:
        print(" ->", os.path.basename(a))

    if len(archivos) < 2:
        raise FileNotFoundError(f"Se necesitan al menos 2 archivos en {carpeta_bandas}")

    # Cargar todas las observaciones de la carpeta
    observaciones = [load_spherex_observation(f) for f in archivos]

    # Ejecutar el pipeline pasando las observaciones que comparten campo en el cielo
    resultado = analyze_observations(observaciones[:2])
    print(json.dumps(resultado, indent=2))

    # =========================================================
    # VISUALIZACIÓN: Marcar candidatos con cuadros rojos
    # =========================================================
    candidatos = resultado.get("candidates", [])
    if candidatos:
        output_dir = Path(__file__).resolve().parent
        output_file = str(output_dir / "candidates_marked.png")
        visualize_candidates_on_image(
            observation=observaciones[0],
            candidates=candidatos,
            output_path=output_file,
            box_half_size=8,
            show_plot=True
        )
    else:
        print("\n[!] No se encontraron candidatos para visualizar.")