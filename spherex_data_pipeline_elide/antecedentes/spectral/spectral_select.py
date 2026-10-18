"""Flujo selectivo de grupos espectrales SPHEREx (CLI paralelo).

No sustituye a ``python -m spherex_pipeline``. El extractor original
(``get_observations`` / ``run_pipeline``) sigue intacto.

Flujo:
- Consulta, clasifica y procesa las imágenes del canal espectral solicitado.
- Aplica lectura rápida mediante mapeo de memoria (``memmap=True``) omitiendo el cubo PSF.
- Tolera caídas HTTP 503 con fallback inmediato sin interrumpir la ejecución.
- Convierte las matrices astronómicas 2D a archivos PNG listos para el Frontend.
- Mide tiempo de ejecución, memoria RAM y velocidad de generación de imágenes.

Ejecutar::

    python -m spherex_pipeline.spectral_select --group 7
    python -m spherex_pipeline.spectral_select --source demo --group 1
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import time
import tracemalloc
import warnings
from typing import Any

from astropy.io import fits
from astropy.time import Time
from astropy.visualization import AsinhStretch, ZScaleInterval
import matplotlib

matplotlib.use("Agg")
import numpy as np
from PIL import Image

from spherex_pipeline.constants import (
    CACHE_DIR,
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DEFAULT_SOURCE,
    DEMO_DEC,
    DEMO_RA,
    DEMO_SIZE_DEG,
    PROJECT_DIR,
    SPECTRAL_UNIT,
)
from spherex_pipeline.cutouts import cutout_region, homogenize_shapes
from spherex_pipeline.demo import load_demo_observations
from spherex_pipeline.irsa import (
    dedupe_records,
    download_cutout,
    query_observations,
)
from spherex_pipeline.masking import apply_invalid_mask
from spherex_pipeline.models import Observation

warnings.filterwarnings("ignore", message=".*SIP distortion.*")

IMAGES_OUTPUT_DIR = PROJECT_DIR / "data" / "images_select"

DETECTOR_RANGES: dict[str, tuple[float, float]] = {
    "SPHEREx-D1": (0.7500, 1.0900),
    "SPHEREx-D2": (1.0880, 1.6560),
    "SPHEREx-D3": (1.6300, 2.4100),
    "SPHEREx-D4": (2.4200, 3.8200),
    "SPHEREx-D5": (3.8300, 4.4100),
    "SPHEREx-D6": (4.4200, 5.0000),
}


class StageProfiler:
    """Context manager para medir tiempo transcurrido y uso de memoria RAM por etapa."""

    def __init__(self, stage_name: str, metrics_list: list[dict[str, Any]]):
        self.stage_name = stage_name
        self.metrics_list = metrics_list

    def __enter__(self):
        tracemalloc.reset_peak()
        self.t0 = time.perf_counter()
        self.mem_before, _ = tracemalloc.get_traced_memory()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        t1 = time.perf_counter()
        mem_after, mem_peak = tracemalloc.get_traced_memory()

        dt = t1 - self.t0
        ram_net_mb = max(0.0, (mem_after - self.mem_before) / (1024 * 1024))
        ram_peak_mb = mem_peak / (1024 * 1024)

        self.metrics_list.append({
            "stage": self.stage_name,
            "duration_s": dt,
            "ram_net_mb": ram_net_mb,
            "ram_peak_mb": ram_peak_mb,
        })


def observation_to_png_file(obs: Observation, output_dir: Path, colormap: str = "inferno") -> Path:
    """Convierte la matriz 2D de una Observation en un archivo PNG optimizado en disco."""
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"survey_{obs.metadata.get('survey_index', 1)}_{obs.id}_{colormap}.png"

    img_data = obs.image
    if img_data is None or img_data.size == 0:
        img = Image.new("RGB", (30, 30), color="black")
        img.save(file_path, format="PNG")
        return file_path

    clean_data = np.nan_to_num(img_data, nan=0.0)
    interval = ZScaleInterval()
    try:
        vmin, vmax = interval.get_limits(clean_data)
    except Exception:
        vmin, vmax = float(np.min(clean_data)), float(np.max(clean_data))

    if vmax <= vmin:
        vmax = vmin + 1e-5

    normalized = np.clip((clean_data - vmin) / (vmax - vmin), 0.0, 1.0)
    stretch = AsinhStretch(a=0.1)
    stretched_data = stretch(normalized)

    cmap = matplotlib.colormaps[colormap]
    rgba_matrix = (cmap(stretched_data) * 255).astype(np.uint8)

    img = Image.fromarray(rgba_matrix)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    img.save(file_path, format="PNG", optimize=True)

    return file_path


def observation_from_fits_fast(
    fits_path: Path | str,
    observation_id: str,
    ra: float,
    dec: float,
    timestamp_mjd: float | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Observation:
    """Lectura FITS con memmap, sin abrir el cubo PSF."""
    extra_metadata = extra_metadata or {}
    file_path = Path(fits_path)

    with fits.open(file_path, memmap=True, lazy_load_hdus=True) as hdul:
        img_data = hdul["IMAGE"].data.astype(np.float32) if "IMAGE" in hdul else hdul[1].data.astype(np.float32)
        flags_data = (
            hdul["FLAGS"].data.astype(np.int32)
            if "FLAGS" in hdul and hdul["FLAGS"].data is not None
            else None
        )
        var_data = (
            hdul["VARIANCE"].data.astype(np.float32)
            if "VARIANCE" in hdul and hdul["VARIANCE"].data is not None
            else None
        )

        hdr = hdul[0].header
        wl_val = extra_metadata.get("wavelength", hdr.get("CRVAL1W", hdr.get("CRVAL3", 0.0)))
        det_num = extra_metadata.get("detector", hdr.get("DETECTOR", 2))

    if timestamp_mjd is not None:
        timestamp = Time(float(timestamp_mjd), format="mjd").isot
    else:
        timestamp = datetime(1970, 1, 1).isoformat()

    try:
        detector = int(det_num)
    except (TypeError, ValueError):
        detector = det_num

    return Observation(
        id=str(observation_id),
        timestamp=timestamp,
        ra=float(ra),
        dec=float(dec),
        detector=detector,
        wavelength=float(wl_val),
        fits_source=str(file_path),
        image=img_data,
        flags=flags_data,
        variance=var_data,
        valid_mask=np.ones_like(img_data, dtype=bool) if img_data is not None else None,
        metadata=extra_metadata,
    )


def calculate_observations_size_mb(observations: list[Observation]) -> tuple[float, int]:
    """Calcula el espacio ocupado en RAM por los arrays NumPy."""
    total_bytes = 0
    total_pixels = 0
    for obs in observations:
        for attr in ("image", "flags", "variance", "valid_mask"):
            val = getattr(obs, attr, None)
            if isinstance(val, np.ndarray):
                total_bytes += val.nbytes
        if obs.image is not None:
            total_pixels += obs.image.size
    return total_bytes / (1024 * 1024), total_pixels


def print_performance_report(
    metrics: list[dict[str, Any]],
    loaded_obs: list[Observation],
    generated_pngs: list[Path],
    output_dir: Path,
    n_real_fits: int,
    n_fallback: int,
) -> None:
    """Imprime el reporte de tiempos por etapa y el origen de cada Observation."""
    total_time = sum(m["duration_s"] for m in metrics)
    max_peak_ram = max((m["ram_peak_mb"] for m in metrics), default=0.0)
    data_mb, total_pixels = calculate_observations_size_mb(loaded_obs)

    col_w_stage = 52
    sep_len = col_w_stage + 14 + 16 + 16

    print("\n" + "=" * sep_len)
    print(" REPORTE DE RENDIMIENTO Y MEDICION DE TIEMPOS")
    print("=" * sep_len)
    print(
        f"{'Etapa del Proceso':<{col_w_stage}} "
        f"{'Tiempo (s)':>12} "
        f"{'RAM Neta (MB)':>15} "
        f"{'Pico RAM (MB)':>15}"
    )
    print("-" * sep_len)

    for m in metrics:
        print(
            f"{m['stage']:<{col_w_stage}} "
            f"{m['duration_s']:>12.4f} "
            f"{m['ram_net_mb']:>15.2f} "
            f"{m['ram_peak_mb']:>15.2f}"
        )

    print("-" * sep_len)
    print(
        f"{'TIEMPO TOTAL HASTA VER LAS IMAGENES (S2E)':<{col_w_stage}} "
        f"{total_time:>12.4f} "
        f"{'—':>15} "
        f"{max_peak_ram:>15.2f}"
    )
    print("=" * sep_len)

    png_size_bytes = sum(p.stat().st_size for p in generated_pngs if p.exists())
    png_size_kb = png_size_bytes / 1024
    png_stage = metrics[-1]["duration_s"] if metrics else 0.0

    print("\n ARCHIVOS RENDERIZADOS Y ORIGEN DE DATOS:")
    print(f"  * Objetos Observation cargados       : {len(loaded_obs)}")
    print(f"  * FITS SPHEREx reales leidos         : {n_real_fits}")
    print(f"  * Fallback demo/sintetico            : {n_fallback}")
    print(f"  * RAM arrays NumPy (nbytes)          : {data_mb:.2f} MB  ({total_pixels} px)")
    print(f"  * Imagenes PNG generadas             : {len(generated_pngs)} archivos")
    print(f"  * Directorio de salida               : {output_dir}")
    print(f"  * Peso total PNG                     : {png_size_kb:.2f} KB")
    print(f"  * Promedio de tiempo por PNG         : {png_stage / max(1, len(generated_pngs)):.4f} s/imagen")
    print("=" * sep_len + "\n")


def get_detector_bins(bandpass: str, n_bins: int = 17) -> list[dict[str, Any]]:
    """Calcula los límites fijos de los 17 bins para el sensor."""
    w_min, w_max = DETECTOR_RANGES.get(bandpass, (1.0880, 1.6560))
    step = (w_max - w_min) / n_bins
    return [
        {
            "group_id": i + 1,
            "wl_min": round(w_min + i * step, 6),
            "wl_max": round(w_min + (i + 1) * step, 6),
            "wl_center": round(w_min + (i + 0.5) * step, 6),
        }
        for i in range(n_bins)
    ]


def get_record_datetime(record: Any) -> datetime:
    """Convierte time_mjd a datetime con soporte para distintos formatos."""
    time_mjd = getattr(record, "time_mjd", None)
    if time_mjd is not None:
        try:
            return Time(float(time_mjd), format="mjd").to_datetime()
        except Exception:
            pass

    ts = getattr(record, "timestamp", None)
    if isinstance(ts, datetime):
        return ts

    ts_str = str(ts or getattr(record, "time_bounds_lower", "")).strip().replace("Z", "")
    if ts_str:
        try:
            return datetime.fromisoformat(ts_str)
        except Exception:
            try:
                return datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass

    return datetime(1970, 1, 1)


def split_records_into_surveys(records: list[Any], gap_days: float = 45.0) -> list[list[Any]]:
    """Agrupa registros cronológicos en Surveys cuando la pausa supera gap_days."""
    if not records:
        return []
    sorted_recs = sorted(records, key=get_record_datetime)
    surveys: list[list[Any]] = []
    current: list[Any] = [sorted_recs[0]]

    for prev, curr in zip(sorted_recs[:-1], sorted_recs[1:]):
        t0 = get_record_datetime(prev)
        t1 = get_record_datetime(curr)
        if (t1 - t0).total_seconds() / 86400.0 > gap_days:
            surveys.append(current)
            current = [curr]
        else:
            current.append(curr)

    if current:
        surveys.append(current)
    return surveys


def print_spectral_groups_table(
    all_bins: list[dict[str, Any]],
    surveys_tap: list[list[Any]],
    selected_group_id: int,
    bandpass: str,
) -> list[list[tuple[Any, float, int]]]:
    """Genera la tabla cruzada de los 17 bins x Surveys."""
    n_bins = len(all_bins)
    n_surveys = len(surveys_tap)
    counts = [[0] * n_surveys for _ in range(n_bins)]
    binned_records: list[list[tuple[Any, float, int]]] = [[] for _ in range(n_bins)]

    for s_idx, survey in enumerate(surveys_tap, start=1):
        n_obs = len(survey)
        for local_idx, rec in enumerate(survey):
            u = local_idx / max(1, n_obs - 1)
            bin_idx = min(n_bins - 1, int(u * n_bins))
            wl = all_bins[bin_idx]["wl_center"]
            counts[bin_idx][s_idx - 1] += 1
            binned_records[bin_idx].append((rec, wl, s_idx))

    col_w = 12
    surveys_header = "".join(f"{f'Survey {s+1}':>{col_w}}" for s in range(n_surveys))
    total_header = f"{'Total':>8}"
    state_header = f"{'  Estado':<18}"
    sep_len = 6 + 23 + 12 + n_surveys * col_w + 8 + 18

    print("\n" + "=" * sep_len)
    print(f"DISTRIBUCION ESPECTRO-TEMPORAL COMPLETA ({bandpass} | {n_bins} Canales x {n_surveys} Surveys)")
    print("=" * sep_len)
    print(
        f"{'Grupo':<6} {'Rango λ (' + SPECTRAL_UNIT + ')':<23} {'λ Centro':<12}"
        + surveys_header
        + total_header
        + state_header
    )
    print("-" * sep_len)

    for i in range(n_bins):
        b = all_bins[i]
        rango = f"{b['wl_min']:.4f} – {b['wl_max']:.4f}"
        centro = f"{b['wl_center']:.4f}"
        row_counts = "".join(f"{counts[i][s]:>{col_w}}" for s in range(n_surveys))
        row_total = sum(counts[i])
        tag = "  <<< SELECCIONADO" if (i + 1) == selected_group_id else ""
        print(f"#{i+1:02d}    {rango:<23} {centro:<12}" + row_counts + f"{row_total:>8}" + tag)

    print("-" * sep_len)
    surveys_totals = "".join(f"{len(surveys_tap[s]):>{col_w}}" for s in range(n_surveys))
    total_global = sum(len(s) for s in surveys_tap)
    print(f"{'Total observaciones':<41}" + surveys_totals + f"{total_global:>8}")
    print("=" * sep_len + "\n")

    return binned_records


def draw_box(title: str, lines: list[str], width: int = 76) -> None:
    """Imprime recuadros visuales en terminal."""
    print(f"+{'-' * (width - 2)}+")
    print(f"| {title:<{width - 4}} |")
    print(f"+{'-' * (width - 2)}+")
    for line in lines:
        print(f"| {line[: width - 4]:<{width - 4}} |")
    print(f"+{'-' * (width - 2)}+\n")


def local_file_exists(url: str | None) -> bool:
    if not url:
        return False
    name = Path(url.split("?")[0]).name
    return (Path(CACHE_DIR) / name).exists()


def _records_from_demo() -> list[Any]:
    observations = load_demo_observations()
    records: list[Any] = []
    for obs in observations:
        try:
            mjd = float(Time(obs.timestamp, format="isot", scale="utc").mjd)
        except Exception:
            mjd = None
        records.append(
            SimpleNamespace(
                time_mjd=mjd,
                timestamp=obs.timestamp,
                obs_id=obs.id,
                cutout_url=None,
                uri="",
                access_url=obs.fits_source,
            )
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Selector de grupos espectrales SPHEREx (CLI paralelo; no reemplaza el pipeline)."
    )
    parser.add_argument("--ra", type=float, default=DEMO_RA)
    parser.add_argument("--dec", type=float, default=DEMO_DEC)
    parser.add_argument("--size", type=float, default=DEMO_SIZE_DEG)
    parser.add_argument("--qr", default=DEFAULT_QR)
    parser.add_argument("--bandpass", default=DEFAULT_BANDPASS)
    parser.add_argument("--group", type=int, default=7, help="Grupo espectral deseado (1 al 17).")
    parser.add_argument("--source", choices=("irsa", "demo"), default=DEFAULT_SOURCE)
    parser.add_argument(
        "--images-dir",
        default=str(IMAGES_OUTPUT_DIR),
        help="Directorio PNG. Default: data/images_select del proyecto.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(CACHE_DIR),
        help="Caché FITS. Default: data/cache del proyecto.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    tracemalloc.start()
    metrics: list[dict[str, Any]] = []

    args = build_parser().parse_args(argv)
    output_dir = Path(args.images_dir)
    cache_path = Path(args.cache_dir)

    if args.group < 1 or args.group > 17:
        print(f"--group debe estar entre 1 y 17; se recibió {args.group}.")
        return 2

    all_bins = get_detector_bins(args.bandpass, n_bins=17)
    det_num = int(args.bandpass.split("-D")[-1]) if "-D" in args.bandpass else 2

    print("1. Consultando catálogo...")
    with StageProfiler("1. Consulta de catalogo (TAP IRSA o demo)", metrics):
        if args.source == "demo":
            records = _records_from_demo()
            print(f"   -> source=demo: {len(records)} épocas sintéticas locales (sin TAP).")
        else:
            raw_records = query_observations(args.ra, args.dec, args.size, qr=args.qr, bandpass=args.bandpass)
            records, _ = dedupe_records(raw_records)
            print(f"   -> TAP IRSA: {len(records)} observaciones catalogadas.")

    if not records:
        print("No se encontraron observaciones.")
        return 0

    with StageProfiler("2. Particion de Surveys y matriz 17 bins", metrics):
        surveys_tap = split_records_into_surveys(records, gap_days=45.0)
        binned_records = print_spectral_groups_table(all_bins, surveys_tap, args.group, args.bandpass)

    matched_records = binned_records[args.group - 1]
    print(f"2. Extrayendo imagenes para el Grupo #{args.group:02d} ({len(matched_records)} observaciones)...")
    if not matched_records:
        occupied = [i + 1 for i, bucket in enumerate(binned_records) if bucket]
        print(f"   -> Este grupo está vacío. Grupos con filas: {occupied}")

    loaded_obs: list[Observation] = []
    irsa_cutout_available = args.source == "irsa"
    n_real_fits = 0
    n_fallback = 0

    with StageProfiler(f"3. Carga y procesamiento FITS (Grupo #{args.group:02d})", metrics):
        for rec, wl_val, s_idx in matched_records:
            dt = get_record_datetime(rec)
            obs_id_val = getattr(rec, "obs_id", None) or getattr(rec, "id", None) or f"obs_{len(loaded_obs)+1}"
            cutout_url_val = getattr(rec, "cutout_url", None) or getattr(rec, "uri", "")

            if irsa_cutout_available and cutout_url_val:
                try:
                    local_file = download_cutout(cutout_url_val, cache_dir=cache_path)
                    extra = {
                        "wavelength": wl_val,
                        "bandwidth": 0.0334,
                        "survey_index": s_idx,
                        "bandpass": args.bandpass,
                        "detector": det_num,
                        "origin": "spherex_fits",
                    }
                    obs = observation_from_fits_fast(
                        local_file,
                        observation_id=str(obs_id_val),
                        ra=args.ra,
                        dec=args.dec,
                        timestamp_mjd=getattr(rec, "time_mjd", None),
                        extra_metadata=extra,
                    )
                    obs = cutout_region(obs, args.ra, args.dec, args.size)
                    if obs.flags is not None:
                        obs.image, obs.valid_mask = apply_invalid_mask(obs.image, obs.flags, obs.variance)
                    loaded_obs.append(obs)
                    n_real_fits += 1
                    print(f"   -> REAL FITS {Path(local_file).name} ({Path(local_file).stat().st_size} B) id={obs_id_val}")
                    continue
                except Exception as exc:
                    print(f"   [Aviso IRSA] {exc}. Activando fallback sin reintentos...")
                    irsa_cutout_available = False

            demo_list = load_demo_observations()
            if demo_list:
                base_demo = demo_list[len(loaded_obs) % len(demo_list)]
                img_data = base_demo.image.copy() if base_demo.image is not None else np.zeros((30, 30), dtype=np.float32)
                flags_data = base_demo.flags.copy() if base_demo.flags is not None else np.zeros((30, 30), dtype=np.int32)
            else:
                rng = np.random.default_rng(hash(str(obs_id_val)) % (2**32))
                img_data = rng.normal(loc=1.2, scale=0.1, size=(30, 30)).astype(np.float32)
                img_data[14:16, 14:16] += 5.0
                flags_data = np.zeros((30, 30), dtype=np.int32)

            obs = Observation(
                id=str(obs_id_val),
                timestamp=dt.isoformat(),
                ra=float(args.ra),
                dec=float(args.dec),
                detector=det_num,
                wavelength=float(wl_val),
                fits_source="fallback_cache" if local_file_exists(cutout_url_val) else "synthetic_survey",
                image=img_data,
                flags=flags_data,
                variance=np.ones_like(img_data, dtype=np.float32) * 0.01,
                valid_mask=np.ones_like(img_data, dtype=bool),
                metadata={
                    "wavelength": wl_val,
                    "bandwidth": 0.0334,
                    "survey_index": s_idx,
                    "bandpass": args.bandpass,
                    "n_invalid_pixels": 0,
                    "origin": "fallback_demo",
                },
            )
            loaded_obs.append(obs)
            n_fallback += 1
            print(f"   -> FALLBACK {obs.fits_source} id={obs_id_val} λ_asignada={wl_val:.4f}")

    with StageProfiler("4. Homogeneizacion y agrupacion por epocas", metrics):
        loaded_obs = homogenize_shapes(loaded_obs)
        surveys_dict: dict[int, list[Observation]] = {}
        for obs in loaded_obs:
            s_id = obs.metadata.get("survey_index", 1)
            surveys_dict.setdefault(s_id, []).append(obs)

    with StageProfiler("5. Renderizado de tarjetas en terminal", metrics):
        print(f"\n3. Visualizacion del canal seleccionado (Grupo #{args.group:02d}):")
        for s_idx in sorted(surveys_dict.keys()):
            obs_item = surveys_dict[s_idx][0]
            meta = obs_item.metadata
            ts_str = str(obs_item.timestamp)[:19]
            shape_str = f"{obs_item.image.shape[0]}x{obs_item.image.shape[1]} px" if obs_item.image is not None else "n/d"

            draw_box(
                f"SURVEY {s_idx} ({ts_str[:10]})",
                [
                    f"Observation ID : {obs_item.id}",
                    f"Fecha y Hora UTC: {ts_str}",
                    f"Longitud Onda λ: {obs_item.wavelength:.6f} {SPECTRAL_UNIT}",
                    f"Ancho Banda Δλ : {meta.get('bandwidth', 0.0334):.6f} {SPECTRAL_UNIT}",
                    f"Dimensiones    : {shape_str} | Detector: SPHEREx-D{obs_item.detector}",
                    f"Fuente de Datos: {obs_item.fits_source}",
                    f"Origen         : {meta.get('origin', 'n/d')}",
                ],
            )

        sorted_keys = sorted(surveys_dict.keys())
        if len(sorted_keys) >= 2:
            obs1 = surveys_dict[sorted_keys[0]][0]
            obs2 = surveys_dict[sorted_keys[1]][0]
            delta_wl = abs(obs1.wavelength - obs2.wavelength)

            draw_box(
                "PAR PARA SUSTRACCION TEMPORAL (IMAGE DIFFERENCING)",
                [
                    f"Survey Referencia : Survey {sorted_keys[0]} (ID: {obs1.id}, λ = {obs1.wavelength:.6f} {SPECTRAL_UNIT})",
                    f"Survey Objetivo   : Survey {sorted_keys[1]} (ID: {obs2.id}, λ = {obs2.wavelength:.6f} {SPECTRAL_UNIT})",
                    f"Diferencia Δλ     : {delta_wl:.6f} {SPECTRAL_UNIT} (asignada por indice, no WCS-WAVE)",
                    f"Estado Operativo  : Matrices 2D homogeneas listas para deteccion de movimiento",
                ],
            )

    generated_pngs: list[Path] = []
    with StageProfiler("6. Generacion de PNG", metrics):
        for obs in loaded_obs:
            png_path = observation_to_png_file(obs, output_dir, colormap="inferno")
            generated_pngs.append(png_path)

    print_performance_report(
        metrics,
        loaded_obs,
        generated_pngs,
        output_dir,
        n_real_fits=n_real_fits,
        n_fallback=n_fallback,
    )
    tracemalloc.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
