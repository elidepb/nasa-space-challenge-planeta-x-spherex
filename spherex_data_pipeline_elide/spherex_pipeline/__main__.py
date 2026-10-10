"""CLI: python -m spherex_pipeline --ra ... --dec ... --size ... --qr qr2 --bandpass SPHEREx-D2"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import sys
from typing import Any
import warnings

from spherex_pipeline.constants import (
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DEFAULT_SOURCE,
    DEMO_DEC,
    DEMO_RA,
    DEMO_SIZE_DEG,
    KNOWN_RELEASES,
    SPECTRAL_UNIT,
)
from spherex_pipeline.demo import build_demo_dataset
from spherex_pipeline.pipeline import get_observations

NOISY_LOGGERS = ("astropy", "astropy.wcs", "astropy.wcs.wcs", "astropy.io.fits")


def silence_astropy() -> None:
    """Suprime registros informativos y advertencias SIP repetitivas de Astropy."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Ignora advertencias recurrentes de distorsión SIP en encabezados FITS
    warnings.filterwarnings("ignore", message=".*SIP distortion.*")
    try:
        from astropy.wcs import FITSFixedWarning

        warnings.filterwarnings("ignore", category=FITSFixedWarning)
    except ImportError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consulta todas las épocas SPHEREx de un QR y una banda para una región.",
    )
    parser.add_argument("--ra", type=float, default=DEMO_RA, help="Ascensión recta en grados.")
    parser.add_argument("--dec", type=float, default=DEMO_DEC, help="Declinación en grados.")
    parser.add_argument("--size", type=float, default=DEMO_SIZE_DEG, help="Tamaño del cutout en grados.")
    parser.add_argument(
        "--qr",
        default=DEFAULT_QR,
        help=f"Quick Release. Valores: {', '.join(KNOWN_RELEASES)}. Default: {DEFAULT_QR}.",
    )
    parser.add_argument(
        "--bandpass",
        default=DEFAULT_BANDPASS,
        help="Banda SPHEREx-D1 ... SPHEREx-D6. Default: SPHEREx-D2.",
    )
    parser.add_argument(
        "--detector",
        type=int,
        default=None,
        help="Alternativa a --bandpass (1-6). Si ambos se indican, deben coincidir.",
    )
    parser.add_argument(
        "--source",
        choices=("irsa", "demo"),
        default=DEFAULT_SOURCE,
        help="irsa consulta NASA/IPAC. demo solo si se pide explícitamente.",
    )
    parser.add_argument(
        "--max-observations",
        type=int,
        default=None,
        help="Tope opcional. Por defecto se descargan todas las épocas TAP.",
    )
    parser.add_argument("--build-demo", action="store_true", help="Regenera el dataset demo local.")
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Imprime la línea completa por observación (id, det, λ, bin, shape, inválidos).",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=17,
        help="Número de bins espectrales para discretizar la banda (default: 17).",
    )
    parser.add_argument(
        "--survey-gap-days",
        type=float,
        default=45.0,
        help="Días de inactividad entre tomas para delimitar un nuevo Survey (default: 45.0).",
    )
    parser.add_argument(
        "--bandwidth-decimals",
        type=int,
        default=3,
        help="Decimales para mostrar Δλ. Default: 3.",
    )
    parser.add_argument("--json", action="store_true", help="Imprime resúmenes JSON enriquecidos.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def parse_timestamp(ts: Any) -> datetime:
    """Convierte cadenas ISO de timestamp a datetime."""
    if isinstance(ts, datetime):
        return ts
    ts_str = str(ts).strip().replace("Z", "")
    try:
        return datetime.fromisoformat(ts_str)
    except Exception:
        return datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")


def split_into_surveys(
    summaries: list[dict[str, Any]], gap_days: float = 45.0
) -> list[list[dict[str, Any]]]:
    """Agrupa observaciones cronológicas en Surveys cuando el salto temporal supera gap_days."""
    if not summaries:
        return []

    sorted_items = sorted(
        summaries,
        key=lambda x: parse_timestamp(x.get("timestamp", "1970-01-01")),
    )

    surveys: list[list[dict[str, Any]]] = []
    current_survey: list[dict[str, Any]] = [sorted_items[0]]

    for prev, curr in zip(sorted_items[:-1], sorted_items[1:]):
        t_prev = parse_timestamp(prev.get("timestamp", "1970-01-01"))
        t_curr = parse_timestamp(curr.get("timestamp", "1970-01-01"))
        diff_days = (t_curr - t_prev).total_seconds() / 86400.0

        if diff_days > gap_days:
            surveys.append(current_survey)
            current_survey = [curr]
        else:
            current_survey.append(curr)

    if current_survey:
        surveys.append(current_survey)

    return surveys


def compute_spectral_bins(
    summaries: list[dict[str, Any]], n_bins: int = 17
) -> tuple[list[float], list[float]]:
    """Calcula los límites (edges) y centros de los N bins espectrales."""
    wavelengths = [
        float(item["wavelength"])
        for item in summaries
        if item.get("wavelength") is not None
    ]
    if not wavelengths:
        return [], []

    w_min = min(wavelengths)
    w_max = max(wavelengths)

    if w_min == w_max:
        return [w_min, w_max], [w_min]

    step = (w_max - w_min) / n_bins
    edges = [w_min + i * step for i in range(n_bins + 1)]
    centers = [(edges[i] + edges[i + 1]) / 2.0 for i in range(n_bins)]
    return edges, centers


def assign_bin(wavelength: float, edges: list[float], n_bins: int) -> int:
    """Asigna una longitud de onda al índice de bin correspondiente (0 a n_bins - 1)."""
    if not edges or len(edges) < 2:
        return 0
    w_min, w_max = edges[0], edges[-1]
    if wavelength >= w_max:
        return n_bins - 1
    if wavelength <= w_min:
        return 0
    bin_idx = int((wavelength - w_min) / (w_max - w_min) * n_bins)
    return max(0, min(n_bins - 1, bin_idx))


def print_survey_bins_report(
    surveys: list[list[dict[str, Any]]],
    bin_edges: list[float],
    bin_centers: list[float],
    n_bins: int,
    bandpass: str,
) -> None:
    """Imprime la tabla cruzada de conteos por Bin espectral y por Survey."""
    if not surveys or not bin_edges:
        print("\nSin datos de longitud de onda para calcular bins.")
        return

    n_surveys = len(surveys)
    total_obs = sum(len(s) for s in surveys)
    w_min, w_max = bin_edges[0], bin_edges[-1]

    # Matriz: [bin_index][survey_index]
    matrix = [[0] * n_surveys for _ in range(n_bins)]
    for s_idx, survey in enumerate(surveys):
        for item in survey:
            b_idx = item.get("bin_index", 1) - 1
            if 0 <= b_idx < n_bins:
                matrix[b_idx][s_idx] += 1

    header_surveys = "".join(f"{f'Survey {s+1}':>12}" for s in range(n_surveys))
    total_col_header = f"{'Total':>8}"
    sep_length = 36 + n_surveys * 12 + 8

    print("\n" + "=" * sep_length)
    print(f"DISTRIBUCIÓN ESPECTRO-TEMPORAL ({n_bins} Bins x {n_surveys} Surveys)")
    print(
        f"Banda: {bandpass} | Rango λ: {w_min:.4f} – {w_max:.4f} {SPECTRAL_UNIT} | "
        f"Total: {total_obs} observaciones"
    )
    print("=" * sep_length)
    print(
        f"{'Bin':<5} {'Rango λ (' + SPECTRAL_UNIT + ')':<21} {'λ Centro':<10}"
        + header_surveys
        + total_col_header
    )
    print("-" * sep_length)

    for i in range(n_bins):
        rango = f"{bin_edges[i]:.4f} – {bin_edges[i+1]:.4f}"
        centro = f"{bin_centers[i]:.4f}"
        counts_str = "".join(f"{matrix[i][s]:>12}" for s in range(n_surveys))
        row_total = sum(matrix[i])
        print(f"#{i+1:02d}  {rango:<21} {centro:<10}" + counts_str + f"{row_total:>8}")

    print("-" * sep_length)
    totals_str = "".join(f"{len(surveys[s]):>12}" for s in range(n_surveys))
    print(f"{'Total observaciones':<36}" + totals_str + f"{total_obs:>8}")
    print("=" * sep_length)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    silence_astropy()

    if args.build_demo:
        path = build_demo_dataset()
        print(f"Dataset demo escrito en {path}")
        return 0

    observations = get_observations(
        args.ra,
        args.dec,
        args.size,
        qr=args.qr,
        bandpass=args.bandpass,
        detector=args.detector,
        source=args.source,
        max_observations=args.max_observations,
    )

    summaries = [obs.to_summary() for obs in observations]
    if not summaries:
        print("No se encontraron observaciones para las coordenadas indicadas.")
        return 0

    # 1. Separar en épocas/Surveys
    surveys = split_into_surveys(summaries, gap_days=args.survey_gap_days)

    # 2. Calcular los N bins globales de longitud de onda
    bin_edges, bin_centers = compute_spectral_bins(summaries, n_bins=args.bins)

    # 3. Anotar cada observación con su Survey y Bin
    for s_idx, survey in enumerate(surveys, start=1):
        for item in survey:
            item["survey_index"] = s_idx
            item["survey_name"] = f"Survey {s_idx}"
            if item.get("wavelength") is not None:
                wl = float(item["wavelength"])
                b_idx = assign_bin(wl, bin_edges, args.bins)
                item["bin_index"] = b_idx + 1
                item["bin_wl_min"] = round(bin_edges[b_idx], 6)
                item["bin_wl_max"] = round(bin_edges[b_idx + 1], 6)
                item["bin_wl_center"] = round(bin_centers[b_idx], 6)

    # Si se pide JSON, emitir todos los registros enriquecidos
    if args.json:
        json.dump(summaries, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # 4. Listado cronológico agrupado visualmente por Survey
    print(
        f"\n{len(summaries)} observaciones recuperadas "
        f"({len(surveys)} Surveys detectados)\n"
    )
    for s_idx, survey in enumerate(surveys, start=1):
        t_start = parse_timestamp(survey[0]["timestamp"]).strftime("%Y-%m-%d")
        t_end = parse_timestamp(survey[-1]["timestamp"]).strftime("%Y-%m-%d")
        print(f"--- Survey {s_idx} ({t_start} a {t_end}) | {len(survey)} tomas ---")

        for item in survey:
            wl = float(item["wavelength"]) if item.get("wavelength") is not None else 0.0
            bin_tag = f"Bin #{item.get('bin_index', 0):02d}"
            bw = (
                f"Δλ={float(item['bandwidth']):.{args.bandwidth_decimals}f} {SPECTRAL_UNIT}"
                if item.get("bandwidth") is not None
                else ""
            )

            if args.detail:
                print(
                    f"   {item['id']:22} {item['timestamp']:24} det={item['detector']} "
                    f"λ={wl:.6f} {SPECTRAL_UNIT}  {bin_tag}  {bw}  "
                    f"shape={item['shape']} invalid={item['n_invalid_pixels']}"
                )
            else:
                print(
                    f"   {item['timestamp']:24}  λ={wl:.4f} {SPECTRAL_UNIT}  "
                    f"{bin_tag}  {bw}"
                )
        print()

    # 5. Imprimir la matriz de Bins vs Surveys
    print_survey_bins_report(
        surveys,
        bin_edges,
        bin_centers,
        n_bins=args.bins,
        bandpass=args.bandpass,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
