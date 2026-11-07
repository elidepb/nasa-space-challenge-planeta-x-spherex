"""PNG de diagnóstico de candidatos sobre un Observation de Elide."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

from astro_pipeline.contracts import Observation
from astro_pipeline.gaussian import smooth_gaussian_np


def visualize_candidates_on_image(
    observation: Observation,
    candidates: list[dict[str, Any]],
    output_path: str = "candidates_marked.png",
    box_half_size: int = 8,
    show_plot: bool = True,
) -> str:
    if not show_plot:
        matplotlib.use("Agg")

    wcs = observation.wcs()
    if wcs is None:
        raise ValueError(f"Observation {observation.id!r} no trae wcs()")

    img_raw = np.array(observation.image, dtype=float, copy=True)
    if observation.valid_mask is not None:
        img_raw[~np.asarray(observation.valid_mask, dtype=bool)] = np.nan

    fill = np.nanmedian(img_raw)
    img_smooth = smooth_gaussian_np(np.nan_to_num(img_raw, nan=fill), sigma=0.6)
    img_display = _asinh_stretch(img_smooth, q=0.005)
    cmap_astro = LinearSegmentedColormap.from_list(
        "spherex_infrared",
        [
            (0.00, "#050510"),
            (0.10, "#0a0a2e"),
            (0.25, "#1a0a3a"),
            (0.40, "#3d0c5c"),
            (0.55, "#8b1a4a"),
            (0.70, "#c44e2b"),
            (0.82, "#e8a020"),
            (0.92, "#f5dc58"),
            (1.00, "#fffff0"),
        ],
        N=512,
    )

    cand_pixels = []
    for cand in candidates:
        payload = asdict(cand) if not isinstance(cand, dict) else cand
        ra, dec = payload.get("ra"), payload.get("dec")
        if ra is None or dec is None:
            continue
        try:
            px, py = wcs.world_to_pixel(SkyCoord(ra=ra, dec=dec, unit="deg"))
            px, py = float(px), float(py)
        except Exception:
            continue
        ny, nx = img_display.shape
        if 0 <= px < nx and 0 <= py < ny:
            cand_pixels.append({**payload, "_px": px, "_py": py})

    n_zoom = min(len(cand_pixels), 6)
    if n_zoom > 0:
        fig = plt.figure(figsize=(16, 10), facecolor="#08090d")
        gs = GridSpec(max(n_zoom, 2), 4, figure=fig, wspace=0.35, hspace=0.4)
        ax_main = fig.add_subplot(gs[:, :3], projection=wcs)
    else:
        fig, ax_main = plt.subplots(1, 1, figsize=(12, 10), subplot_kw={"projection": wcs})
        fig.patch.set_facecolor("#08090d")
        gs = None

    ax_main.imshow(
        img_display, origin="lower", cmap=cmap_astro,
        vmin=0, vmax=1, interpolation="bicubic", aspect="equal",
    )
    ax_main.set_facecolor("#050510")
    ax_main.coords[0].set_axislabel("Right Ascension (J2000)", fontsize=11, color="#cccccc")
    ax_main.coords[1].set_axislabel("Declination (J2000)", fontsize=11, color="#cccccc")
    ax_main.coords[0].set_ticklabel(color="#999999", size=9)
    ax_main.coords[1].set_ticklabel(color="#999999", size=9)
    ax_main.coords.grid(color="#ffffff", alpha=0.08, linestyle="-", linewidth=0.5)
    ax_main.set_title(
        "SPHEREx — Moving Object Candidate Detection",
        fontsize=15, fontweight="bold", color="#e8e8f0", pad=15, fontfamily="monospace",
    )

    marker_colors = ["#ff2d2d", "#ff6b35", "#ffd23f", "#3bceac", "#0ead69", "#6c5ce7"]
    n_marked = 0
    for idx, cand in enumerate(cand_pixels):
        px, py = cand["_px"], cand["_py"]
        cand_id = cand.get("id", f"C-{idx + 1:03d}")
        color = marker_colors[idx % len(marker_colors)]
        ax_main.add_patch(
            FancyBboxPatch(
                (px - box_half_size, py - box_half_size),
                2 * box_half_size, 2 * box_half_size,
                boxstyle="round,pad=1", linewidth=2.0,
                edgecolor=color, facecolor="none", zorder=10,
            )
        )
        cross = box_half_size * 0.4
        ax_main.plot([px - cross, px + cross], [py, py], color=color, linewidth=1.2, zorder=11)
        ax_main.plot([px, px], [py - cross, py + cross], color=color, linewidth=1.2, zorder=11)
        ax_main.annotate(
            str(cand_id), xy=(px, py + box_half_size + 3),
            fontsize=7.5, color=color, fontweight="bold", ha="center", va="bottom", zorder=12,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#0a0a0a", alpha=0.85, edgecolor=color, linewidth=0.8),
        )
        n_marked += 1

    epoch_label = str(observation.timestamp)[:10]
    ax_main.text(
        0.015, 0.985,
        f"Candidatos detectados: {n_marked}\nÉpoca: {epoch_label}\nCampo: {img_raw.shape[1]}×{img_raw.shape[0]} px",
        transform=ax_main.transAxes, fontsize=9, color="#ff6666", fontfamily="monospace",
        fontweight="bold", verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#0a0a0a", alpha=0.9, edgecolor="#ff4444", linewidth=1.2),
        zorder=20,
    )

    if gs is not None:
        cutout_radius = 15
        for idx in range(n_zoom):
            cand = cand_pixels[idx]
            px, py = int(round(cand["_px"])), int(round(cand["_py"]))
            color = marker_colors[idx % len(marker_colors)]
            ny, nx = img_display.shape
            cutout = img_display[
                max(0, py - cutout_radius):min(ny, py + cutout_radius + 1),
                max(0, px - cutout_radius):min(nx, px + cutout_radius + 1),
            ]
            ax_zoom = fig.add_subplot(gs[idx, 3])
            ax_zoom.imshow(cutout, origin="lower", cmap=cmap_astro, vmin=0, vmax=1, interpolation="bicubic")
            cy, cx = cutout.shape[0] / 2, cutout.shape[1] / 2
            ax_zoom.plot([cx - 2.5, cx + 2.5], [cy, cy], color=color, lw=1.5)
            ax_zoom.plot([cx, cx], [cy - 2.5, cy + 2.5], color=color, lw=1.5)
            for spine in ax_zoom.spines.values():
                spine.set_edgecolor(color)
                spine.set_linewidth(2)
            ax_zoom.set_xticks([])
            ax_zoom.set_yticks([])
            ax_zoom.set_title(
                f"{cand.get('id', f'C-{idx+1:03d}')}  SNR={cand.get('snr', 0):.1f}\n"
                f"{cand.get('motionArcsecPerYear', 0):.2f}\"/yr  Δ={cand.get('displacementArcsec', 0):.2f}\"",
                fontsize=7.5, color=color, fontweight="bold", fontfamily="monospace", pad=4,
            )

    cbar_ax = fig.add_axes([0.03, 0.02, 0.20, 0.015])
    cbar = fig.colorbar(
        matplotlib.cm.ScalarMappable(cmap=cmap_astro),
        cax=cbar_ax,
        orientation="horizontal",
    )
    cbar.set_label("Intensidad relativa (asinh stretch)", fontsize=8, color="#999999")
    cbar.ax.tick_params(labelsize=7, colors="#777777")
    fig.text(
        0.98, 0.01,
        "SPHEREx Pipeline · Planeta X · NASA Space Apps 2026",
        fontsize=7, color="#555555", ha="right", va="bottom", fontfamily="monospace", style="italic",
    )

    abs_path = str(__import__("os").path.abspath(output_path))
    fig.savefig(abs_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\n[OK] Imagen guardada en: {abs_path}")
    print(f"    >> {n_marked} candidatos marcados")
    if show_plot:
        plt.show()
    else:
        plt.close(fig)
    return abs_path


def _asinh_stretch(img: np.ndarray, q: float = 0.01) -> np.ndarray:
    valid = img[np.isfinite(img)]
    if len(valid) == 0:
        return np.zeros_like(img)
    vmin = np.percentile(valid, q * 100)
    vmax = np.percentile(valid, (1 - q) * 100)
    normalized = (np.clip(img, vmin, vmax) - vmin) / max(vmax - vmin, 1e-10)
    a = 0.1
    stretched = np.arcsinh(normalized / a) / np.arcsinh(1.0 / a)
    return np.nan_to_num(stretched, nan=0.0)
