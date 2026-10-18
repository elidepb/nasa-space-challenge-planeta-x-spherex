"""Extractor lean SPHEREx (propuesta), folder aparte.

No modifica spherex_pipeline ni spectral_select.

Pase 1: TAP + HTTP Range de cabecera IMAGE (23 KB) y cola WCS-WAVE (6 KB)
         para λ real en (ra, dec).
Pase 2: HTTP Range de franjas de fila de IMAGE/FLAGS/VARIANCE/ZODI (~1 MB),
         sin cubo PSF. Persiste un FITS chico y PNG.

Uso (venv del pipeline)::

    ../spherex_data_pipeline_elide/.venv/bin/python lean_extract.py --group 7 --size 0.05
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
import urllib.error
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.visualization import AsinhStretch, ZScaleInterval
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales, skycoord_to_pixel
from astropy import units as u
import matplotlib

matplotlib.use("Agg")
from PIL import Image

ROOT = Path(__file__).resolve().parent
PIPELINE_DIR = ROOT.parent / "spherex_data_pipeline_elide"
sys.path.insert(0, str(PIPELINE_DIR))

from spherex_pipeline.constants import (  # noqa: E402
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DEMO_DEC,
    DEMO_RA,
    DEMO_SIZE_DEG,
    SPECTRAL_UNIT,
)
from spherex_pipeline.cutouts import homogenize_shapes  # noqa: E402
from spherex_pipeline.irsa import (  # noqa: E402
    dedupe_records,
    query_observations,
    s3_mef_url,
)
from spherex_pipeline.masking import apply_invalid_mask  # noqa: E402
from spherex_pipeline.models import Observation  # noqa: E402

warnings.filterwarnings("ignore", message=".*SIP distortion.*")
warnings.filterwarnings("ignore", category=Warning)
logging.getLogger("astropy").setLevel(logging.ERROR)
logging.getLogger("astropy.wcs").setLevel(logging.ERROR)

HERE_IMAGES = ROOT / "data" / "images"
HERE_CUTOUTS = ROOT / "data" / "cutouts"

DETECTOR_RANGES: dict[str, tuple[float, float]] = {
    "SPHEREx-D1": (0.7500, 1.0900),
    "SPHEREx-D2": (1.0880, 1.6560),
    "SPHEREx-D3": (1.6300, 2.4100),
    "SPHEREx-D4": (2.4200, 3.8200),
    "SPHEREx-D5": (3.8300, 4.4100),
    "SPHEREx-D6": (4.4200, 5.0000),
}

# Layout medido en MEF Level-2 2040×2040 float32 (archivo 71 634 240 B).
STD_NAXIS = 2040
STD_FILE_SIZE = 71_634_240
STD_IMAGE_HDR = (2880, 23040)  # [start, end) IMAGE header
STD_WCSWAVE_BYTES = 5760
STD_DATA_SPAN = 16_646_400  # 2040*2040*4
STD_LAYOUT = {
    "IMAGE": (23_040, np.float32),
    "FLAGS": (16_683_840, np.int32),
    "VARIANCE": (33_341_760, np.float32),
    "ZODI": (49_999_680, np.float32),
}
ROW_BYTES = STD_NAXIS * 4

# Corridas de spectral_select el 16 Oct 2026, misma región.
SPECTRAL_SELECT_BASELINES = [
    {
        "label": "spectral_select demo --group 1",
        "wall_s": 0.85,
        "tap_s": 0.13,
        "fits_s": 0.14,
        "real_fits": 0,
        "fallback": 1,
        "disk_mb": 0.0,
        "png_kb": 8.22,
        "shape": "64x64",
        "lambda_source": "índice temporal (no SPHEREx)",
    },
    {
        "label": "spectral_select irsa --size 0.02 (caché)",
        "wall_s": 10.52,
        "tap_s": 9.83,
        "fits_s": 0.07,
        "real_fits": 6,
        "fallback": 0,
        "disk_mb": 6 * 5.060,
        "png_kb": 2.86,
        "shape": "12x12",
        "lambda_source": "centro de cubeta, no WCS-WAVE",
    },
    {
        "label": "spectral_select irsa --size 0.05 (IBE)",
        "wall_s": 135.06,
        "tap_s": 9.48,
        "fits_s": 124.95,
        "real_fits": 5,
        "fallback": 1,
        "disk_mb": 5 * 5.072,
        "png_kb": 17.96,
        "shape": "64x64 (demo contaminó)",
        "lambda_source": "centro de cubeta, no WCS-WAVE",
    },
]


class StageProfiler:
    def __init__(self, stage_name: str, metrics_list: list[dict[str, Any]]):
        self.stage_name = stage_name
        self.metrics_list = metrics_list

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.metrics_list.append(
            {"stage": self.stage_name, "duration_s": time.perf_counter() - self.t0}
        )


@dataclass
class TransferStats:
    bytes: int = 0
    requests: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, n_bytes: int, n_req: int = 1) -> None:
        with self._lock:
            self.bytes += n_bytes
            self.requests += n_req


@dataclass
class WaveSample:
    url: str
    s3_url: str
    record: Any
    wavelength_um: float
    bandwidth_um: float | None
    timestamp: str
    pixel_x: float
    pixel_y: float
    in_frame: bool
    header: fits.Header
    file_size: int
    bytes_xfer: int


def http_range(url: str, start: int, end: int, timeout: float, stats: TransferStats) -> tuple[bytes, int]:
    """GET bytes=start-end inclusive. Devuelve (payload, tamaño_total)."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read()
                content_range = response.headers.get("Content-Range") or ""
            total = int(content_range.split("/")[-1]) if "/" in content_range else end + 1
            stats.add(len(payload), 1)
            return payload, total
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Range falló {url} [{start}-{end}]: {last_exc}") from last_exc


def get_detector_bins(bandpass: str, n_bins: int = 17) -> list[dict[str, Any]]:
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


def assign_bin(wavelength: float, bins: list[dict[str, Any]]) -> int:
    if not bins:
        return 0
    if wavelength >= bins[-1]["wl_max"]:
        return len(bins) - 1
    for i, item in enumerate(bins):
        if wavelength < item["wl_max"]:
            return i
    return len(bins) - 1


def record_datetime(record: Any) -> datetime:
    if record.time_mjd is not None:
        return Time(float(record.time_mjd), format="mjd").to_datetime()
    return datetime(1970, 1, 1)


def split_surveys(records: list[Any], gap_days: float = 45.0) -> list[list[Any]]:
    if not records:
        return []
    ordered = sorted(records, key=record_datetime)
    surveys: list[list[Any]] = []
    current = [ordered[0]]
    for prev, curr in zip(ordered[:-1], ordered[1:]):
        delta = (record_datetime(curr) - record_datetime(prev)).total_seconds() / 86400.0
        if delta > gap_days:
            surveys.append(current)
            current = [curr]
        else:
            current.append(curr)
    surveys.append(current)
    return surveys


def quantity_to_um(value: Any) -> float:
    if hasattr(value, "to"):
        return float(value.to(u.um).value)
    return float(np.asarray(value).reshape(-1)[0])


def wavelength_from_header_and_tail(
    image_hdr: fits.Header, tail: bytes, ra: float, dec: float
) -> tuple[float, float | None, float, float, bool]:
    wave = fits.open(BytesIO(tail), ignore_missing_simple=True)[0]
    wave.name = "WCS-WAVE"
    tiny = fits.HDUList(
        [fits.PrimaryHDU(), fits.ImageHDU(data=None, header=image_hdr), wave]
    )
    spatial = WCS(image_hdr, naxis=2, relax=True)
    nx = int(image_hdr["NAXIS1"])
    ny = int(image_hdr["NAXIS2"])
    x, y = skycoord_to_pixel(
        SkyCoord(ra=ra, dec=dec, unit="deg", frame="icrs"), spatial, origin=0
    )
    px, py = float(x), float(y)
    in_frame = 0.0 <= px < nx and 0.0 <= py < ny
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        spectral = WCS(header=image_hdr, fobj=tiny, key="W")
        spectral.sip = None
        world = spectral.pixel_to_world(px, py)
    if isinstance(world, (list, tuple)):
        wl = quantity_to_um(world[0])
        bw = quantity_to_um(world[1]) if len(world) > 1 else None
    else:
        wl = quantity_to_um(getattr(world, "wavelength", world))
        extra = getattr(world, "bandwidth", None)
        bw = quantity_to_um(extra) if extra is not None else None
    return wl, bw, px, py, in_frame


def sample_wavelength(record: Any, ra: float, dec: float, timeout: float, stats: TransferStats) -> WaveSample:
    s3_url = s3_mef_url(record.access_url)
    if not s3_url:
        raise RuntimeError(f"Sin URL S3 para {record.access_url}")
    head, total = http_range(s3_url, 0, STD_IMAGE_HDR[1] - 1, timeout, stats)
    if len(head) < STD_IMAGE_HDR[1]:
        raise RuntimeError("Cabecera IMAGE incompleta")
    image_hdr = fits.Header.fromstring(head[STD_IMAGE_HDR[0] : STD_IMAGE_HDR[1]])
    if int(image_hdr.get("NAXIS1", 0)) != STD_NAXIS or int(image_hdr.get("NAXIS2", 0)) != STD_NAXIS:
        raise RuntimeError(
            f"NAXIS inesperado {image_hdr.get('NAXIS1')}x{image_hdr.get('NAXIS2')}"
        )
    if int(image_hdr.get("BITPIX", 0)) != -32:
        raise RuntimeError(f"BITPIX inesperado {image_hdr.get('BITPIX')}")
    if total < STD_IMAGE_HDR[1] + STD_WCSWAVE_BYTES:
        raise RuntimeError(f"MEF demasiado corto: {total} B")
    tail, _ = http_range(s3_url, total - STD_WCSWAVE_BYTES, total - 1, timeout, stats)
    wl, bw, px, py, in_frame = wavelength_from_header_and_tail(image_hdr, tail, ra, dec)
    timestamp = str(image_hdr.get("DATE-OBS") or image_hdr.get("DATE") or "")
    if not timestamp and record.time_mjd is not None:
        timestamp = Time(float(record.time_mjd), format="mjd").isot
    return WaveSample(
        url=record.access_url,
        s3_url=s3_url,
        record=record,
        wavelength_um=float(wl),
        bandwidth_um=None if bw is None else float(bw),
        timestamp=timestamp,
        pixel_x=px,
        pixel_y=py,
        in_frame=in_frame,
        header=image_hdr,
        file_size=total,
        bytes_xfer=len(head) + len(tail),
    )


def cutout_science(
    sample: WaveSample,
    ra: float,
    dec: float,
    size_deg: float,
    timeout: float,
    stats: TransferStats,
) -> dict[str, Any]:
    spatial = WCS(sample.header, naxis=2, relax=True)
    scale = float(np.mean(np.abs(proj_plane_pixel_scales(spatial))))
    npix = max(8, int(np.ceil(size_deg / scale)))
    x, y = skycoord_to_pixel(
        SkyCoord(ra=ra, dec=dec, unit="deg", frame="icrs"), spatial, origin=0
    )
    px, py = float(x), float(y)
    y0 = int(np.floor(py - npix / 2.0))
    x0 = int(np.floor(px - npix / 2.0))
    y1, x1 = y0 + npix, x0 + npix
    y0c, y1c = max(0, y0), min(STD_NAXIS, y1)
    x0c, x1c = max(0, x0), min(STD_NAXIS, x1)
    arrays: dict[str, np.ndarray] = {}
    for name, (dat_loc, dtype) in STD_LAYOUT.items():
        start = dat_loc + y0c * ROW_BYTES
        end = dat_loc + y1c * ROW_BYTES - 1
        blob, _ = http_range(sample.s3_url, start, end, timeout, stats)
        ny = y1c - y0c
        rows = np.frombuffer(blob, dtype=dtype).reshape(ny, STD_NAXIS)
        arrays[name] = np.array(rows[:, x0c:x1c], copy=True)
    cut_wcs = spatial[y0c:y1c, x0c:x1c]
    return {
        "arrays": arrays,
        "wcs": cut_wcs,
        "npix": npix,
        "x0": x0c,
        "y0": y0c,
        "shape": arrays["IMAGE"].shape,
    }


def write_small_fits(path: Path, cut: dict[str, Any], sample: WaveSample) -> int:
    image_header = cut["wcs"].to_header(relax=True)
    image_header["DATE-OBS"] = sample.timestamp
    image_header["BUNIT"] = sample.header.get("BUNIT", "MJy / sr")
    hdus = [
        fits.PrimaryHDU(),
        fits.ImageHDU(data=cut["arrays"]["IMAGE"], header=image_header, name="IMAGE"),
        fits.ImageHDU(data=cut["arrays"]["FLAGS"], name="FLAGS"),
        fits.ImageHDU(data=cut["arrays"]["VARIANCE"], name="VARIANCE"),
        fits.ImageHDU(data=cut["arrays"]["ZODI"], name="ZODI"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList(hdus).writeto(path, overwrite=True)
    return path.stat().st_size


def observation_from_cut(
    cut: dict[str, Any], sample: WaveSample, ra: float, dec: float, extra: dict[str, Any]
) -> Observation:
    image = np.array(cut["arrays"]["IMAGE"], dtype=float)
    flags = np.array(cut["arrays"]["FLAGS"])
    variance = np.array(cut["arrays"]["VARIANCE"], dtype=float)
    image, valid = apply_invalid_mask(image, flags, variance)
    wcs_header = dict(cut["wcs"].to_header(relax=True))
    det = extra.get("detector", sample.header.get("DETECTOR", 2))
    try:
        det = int(det)
    except (TypeError, ValueError):
        pass
    obs_id = Path(sample.s3_url).name.replace(".fits", "")
    metadata = {
        **extra,
        "wavelength_source": "WCS-WAVE (Range, píxel de (ra, dec))",
        "origin": "spherex_s3_range",
        "has_variance": True,
        "has_flags": True,
        "cutout_npix": cut["npix"],
    }
    return Observation(
        id=obs_id,
        timestamp=sample.timestamp,
        ra=float(ra),
        dec=float(dec),
        detector=det,
        wavelength=sample.wavelength_um,
        image=image,
        fits_source=str(extra.get("local_path", sample.s3_url)),
        metadata=metadata,
        flags=flags,
        variance=variance,
        zodi=np.array(cut["arrays"]["ZODI"], dtype=float),
        valid_mask=valid,
        cutout=image,
        wcs_header=wcs_header,
        bandwidth=sample.bandwidth_um,
        wavelength_source="WCS-WAVE (Range, píxel de (ra, dec))",
        bandwidth_source="WCS-WAVE (Range, píxel de (ra, dec))",
        spectral_calibration_source="WCS-WAVE",
    )


def observation_to_png(obs: Observation, output_dir: Path, colormap: str = "inferno") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"survey_{obs.metadata.get('survey_index', 1)}_{obs.id}_{colormap}.png"
    img_data = obs.image
    if img_data is None or img_data.size == 0:
        Image.new("RGB", (30, 30), color="black").save(file_path, format="PNG")
        return file_path
    clean = np.nan_to_num(img_data, nan=0.0)
    try:
        vmin, vmax = ZScaleInterval().get_limits(clean)
    except Exception:
        vmin, vmax = float(np.min(clean)), float(np.max(clean))
    if vmax <= vmin:
        vmax = vmin + 1e-5
    stretched = AsinhStretch(a=0.1)(np.clip((clean - vmin) / (vmax - vmin), 0.0, 1.0))
    rgba = (matplotlib.colormaps[colormap](stretched) * 255).astype(np.uint8)
    img = Image.fromarray(rgba).transpose(Image.FLIP_TOP_BOTTOM)
    img.save(file_path, format="PNG", optimize=True)
    return file_path


def print_real_bin_table(
    bins: list[dict[str, Any]],
    surveys: list[list[Any]],
    samples_by_url: dict[str, WaveSample],
    selected_group: int,
    bandpass: str,
) -> None:
    n_bins, n_surveys = len(bins), len(surveys)
    counts = [[0] * n_surveys for _ in range(n_bins)]
    for s_idx, survey in enumerate(surveys):
        for rec in survey:
            sample = samples_by_url.get(rec.access_url)
            if sample is None or not sample.in_frame:
                continue
            counts[assign_bin(sample.wavelength_um, bins)][s_idx] += 1
    col_w = 12
    header = "".join(f"{f'Survey {s+1}':>{col_w}}" for s in range(n_surveys))
    sep = 6 + 23 + 12 + n_surveys * col_w + 8 + 18
    print("\n" + "=" * sep)
    print(f"BINS REALES WCS-WAVE ({bandpass} | {n_bins} x {n_surveys} surveys)")
    print("=" * sep)
    print(f"{'Grupo':<6} {'Rango λ (' + SPECTRAL_UNIT + ')':<23} {'λ Centro':<12}" + header + f"{'Total':>8}{'  Estado':<18}")
    print("-" * sep)
    for i, b in enumerate(bins):
        row = "".join(f"{counts[i][s]:>{col_w}}" for s in range(n_surveys))
        tag = "  <<< SELECCIONADO" if (i + 1) == selected_group else ""
        print(
            f"#{i+1:02d}    {b['wl_min']:.4f} – {b['wl_max']:.4f}         {b['wl_center']:.4f}    "
            + row
            + f"{sum(counts[i]):>8}"
            + tag
        )
    print("=" * sep + "\n")


def select_group(
    surveys: list[list[Any]],
    samples_by_url: dict[str, WaveSample],
    bins: list[dict[str, Any]],
    group: int,
    max_per_survey: int,
) -> list[tuple[Any, WaveSample, int]]:
    target = bins[group - 1]
    chosen: list[tuple[Any, WaveSample, int]] = []
    for s_idx, survey in enumerate(surveys, start=1):
        members: list[tuple[Any, WaveSample]] = []
        for rec in survey:
            sample = samples_by_url.get(rec.access_url)
            if sample is None or not sample.in_frame:
                continue
            if target["wl_min"] <= sample.wavelength_um < target["wl_max"] or (
                group == len(bins) and sample.wavelength_um <= target["wl_max"]
            ):
                members.append((rec, sample))
        members.sort(key=lambda item: abs(item[1].wavelength_um - target["wl_center"]))
        for rec, sample in members[:max_per_survey]:
            chosen.append((rec, sample, s_idx))
    if chosen:
        return chosen
    # Si el bin real está vacío, 1 época por survey más cercana al centro (sigue siendo λ real).
    print(f"   Grupo #{group:02d} vacío en λ real; se toma 1 época/survey más cercana a {target['wl_center']:.4f} μm")
    for s_idx, survey in enumerate(surveys, start=1):
        scored: list[tuple[float, Any, WaveSample]] = []
        for rec in survey:
            sample = samples_by_url.get(rec.access_url)
            if sample is None or not sample.in_frame:
                continue
            scored.append((abs(sample.wavelength_um - target["wl_center"]), rec, sample))
        scored.sort(key=lambda item: item[0])
        if scored:
            _, rec, sample = scored[0]
            chosen.append((rec, sample, s_idx))
    return chosen


def print_report(metrics: list[dict[str, Any]], stats: TransferStats, loaded: list[Observation], pngs: list[Path], cutout_dir: Path) -> None:
    total = sum(m["duration_s"] for m in metrics)
    disk = sum(p.stat().st_size for p in cutout_dir.glob("*.fits")) if cutout_dir.exists() else 0
    png_bytes = sum(p.stat().st_size for p in pngs if p.exists())
    sep = 90
    print("\n" + "=" * sep)
    print(" REPORTE LEAN (Range S3, sin PSF)")
    print("=" * sep)
    print(f"{'Etapa':<52} {'Tiempo (s)':>12}")
    print("-" * sep)
    for m in metrics:
        print(f"{m['stage']:<52} {m['duration_s']:>12.4f}")
    print("-" * sep)
    print(f"{'TOTAL':<52} {total:>12.4f}")
    print("=" * sep)
    print(f"  Observaciones reales     : {len(loaded)}")
    print(f"  Fallback demo            : 0")
    print(f"  HTTP Range requests      : {stats.requests}")
    print(f"  Bytes transferidos       : {stats.bytes / (1024*1024):.2f} MB ({stats.bytes} B)")
    print(f"  FITS persistidos         : {disk / 1024:.1f} KB ({cutout_dir})")
    print(f"  PNG                      : {png_bytes / 1024:.2f} KB ({len(pngs)} archivos)")
    if loaded:
        wls = [obs.wavelength for obs in loaded]
        print(f"  λ real min–max           : {min(wls):.6f} – {max(wls):.6f} {SPECTRAL_UNIT}")
        print(f"  Δλ entre extremos        : {max(wls) - min(wls):.6f} {SPECTRAL_UNIT}")
        print(f"  shape                    : {loaded[0].image.shape}")
        print(f"  WCS presente             : {loaded[0].wcs() is not None}")
    print("=" * sep + "\n")


def print_comparison(wall_s: float, metrics: list[dict[str, Any]], stats: TransferStats, loaded: list[Observation], pngs: list[Path], cutout_dir: Path) -> None:
    tap = next((m["duration_s"] for m in metrics if m["stage"].startswith("1.")), 0.0)
    fits_t = sum(m["duration_s"] for m in metrics if m["stage"].startswith(("3.", "5.")))
    disk_mb = (sum(p.stat().st_size for p in cutout_dir.glob("*.fits")) if cutout_dir.exists() else 0) / (1024 * 1024)
    png_kb = sum(p.stat().st_size for p in pngs if p.exists()) / 1024
    shape = "n/d" if not loaded else f"{loaded[0].image.shape[0]}x{loaded[0].image.shape[1]}"
    rows = SPECTRAL_SELECT_BASELINES + [
        {
            "label": "LEAN Range S3 (esta corrida)",
            "wall_s": wall_s,
            "tap_s": tap,
            "fits_s": fits_t,
            "real_fits": len(loaded),
            "fallback": 0,
            "disk_mb": disk_mb,
            "png_kb": png_kb,
            "shape": shape,
            "lambda_source": "WCS-WAVE en (ra,dec)",
        }
    ]
    print("COMPARACION vs spectral_select (misma región M101 QR2 D2, 16 Oct 2026)")
    print(
        f"{'Corrida':<48} {'wall s':>8} {'TAP s':>8} {'FITS s':>8} {'reales':>7} {'fake':>5} {'disco MB':>10} {'PNG KB':>8}"
    )
    for row in rows:
        print(
            f"{row['label']:<48} {row['wall_s']:>8.2f} {row['tap_s']:>8.2f} {row['fits_s']:>8.2f} "
            f"{row['real_fits']:>7} {row['fallback']:>5} {row['disk_mb']:>10.2f} {row['png_kb']:>8.2f}"
        )
    print()
    ibe = SPECTRAL_SELECT_BASELINES[-1]
    if wall_s > 0 and ibe["wall_s"] > 0:
        print(f"  wall vs IBE spectral_select : {ibe['wall_s'] / wall_s:.1f}× más rápido")
        print(f"  disco vs IBE spectral_select: {ibe['disk_mb'] / max(disk_mb, 1e-9):.0f}× menos MB persistidos")
        print(f"  transferido HTTP            : {stats.bytes / (1024*1024):.2f} MB  (IBE bajó ~25 MB de PSF)")
    print()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extractor lean SPHEREx por HTTP Range, sin PSF.")
    p.add_argument("--ra", type=float, default=DEMO_RA)
    p.add_argument("--dec", type=float, default=DEMO_DEC)
    p.add_argument("--size", type=float, default=DEMO_SIZE_DEG)
    p.add_argument("--qr", default=DEFAULT_QR)
    p.add_argument("--bandpass", default=DEFAULT_BANDPASS)
    p.add_argument("--group", type=int, default=7)
    p.add_argument("--max-per-survey", type=int, default=2)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--images-dir", default=str(HERE_IMAGES))
    p.add_argument("--cutouts-dir", default=str(HERE_CUTOUTS))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.group < 1 or args.group > 17:
        print("--group debe estar entre 1 y 17")
        return 2
    images_dir = Path(args.images_dir)
    cutouts_dir = Path(args.cutouts_dir)
    cutouts_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    metrics: list[dict[str, Any]] = []
    stats = TransferStats()
    wall0 = time.perf_counter()
    bins = get_detector_bins(args.bandpass)
    det_num = int(args.bandpass.split("-D")[-1]) if "-D" in args.bandpass else 2

    print("1. Consultando TAP IRSA...")
    with StageProfiler("1. Consulta TAP IRSA", metrics):
        records, _ = dedupe_records(
            query_observations(args.ra, args.dec, args.size, qr=args.qr, bandpass=args.bandpass)
        )
    print(f"   -> {len(records)} productos catalogados.")
    if not records:
        return 0

    with StageProfiler("2. Particion de surveys", metrics):
        surveys = split_surveys(records)
    print(f"   -> {len(surveys)} surveys (hueco > 45 d).")

    print(f"3. Pase 1: λ WCS-WAVE por Range ({args.workers} hilos, ~29 KB/archivo)...")
    samples_by_url: dict[str, WaveSample] = {}
    n_fail = 0
    with StageProfiler("3. Pase 1 λ WCS-WAVE (HTTP Range)", metrics):
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futs = {
                pool.submit(sample_wavelength, rec, args.ra, args.dec, args.timeout, stats): rec
                for rec in records
            }
            done = 0
            for fut in as_completed(futs):
                rec = futs[fut]
                done += 1
                try:
                    sample = fut.result()
                    samples_by_url[rec.access_url] = sample
                except Exception as exc:
                    n_fail += 1
                    if n_fail <= 3:
                        print(f"   [pase1] {Path(rec.access_url).name}: {exc}")
                if done % 20 == 0 or done == len(records):
                    print(f"   ... {done}/{len(records)}  ok={len(samples_by_url)} fail={n_fail}  {stats.bytes/1024:.0f} KB")

    in_frame = sum(1 for s in samples_by_url.values() if s.in_frame)
    print(f"   -> λ reales: {len(samples_by_url)}  en el recorte: {in_frame}  fallos: {n_fail}")
    print_real_bin_table(bins, surveys, samples_by_url, args.group, args.bandpass)

    selected = select_group(surveys, samples_by_url, bins, args.group, args.max_per_survey)
    print(f"4. Grupo #{args.group:02d}: {len(selected)} épocas a recortar (máx {args.max_per_survey}/survey)")

    loaded: list[Observation] = []
    with StageProfiler("5. Pase 2 cutout ciencia sin PSF (HTTP Range)", metrics):
        for rec, sample, s_idx in selected:
            name = Path(sample.s3_url).name
            try:
                cut = cutout_science(sample, args.ra, args.dec, args.size, args.timeout, stats)
                dest = cutouts_dir / name.replace(".fits", "_lean.fits")
                nbytes = write_small_fits(dest, cut, sample)
                extra = {
                    "survey_index": s_idx,
                    "bandpass": args.bandpass,
                    "detector": det_num,
                    "local_path": str(dest),
                    "group": args.group,
                }
                obs = observation_from_cut(cut, sample, args.ra, args.dec, extra)
                loaded.append(obs)
                print(
                    f"   REAL {name}  λ={sample.wavelength_um:.6f} μm  "
                    f"shape={cut['shape']}  {nbytes} B  survey={s_idx}"
                )
            except Exception as exc:
                print(f"   [pase2] {name}: {exc}")
                traceback.print_exc()

    with StageProfiler("6. Homogeneizar y PNG", metrics):
        loaded = homogenize_shapes(loaded)
        pngs = [observation_to_png(obs, images_dir) for obs in loaded]

    wall = time.perf_counter() - wall0
    print_report(metrics, stats, loaded, pngs, cutouts_dir)
    print_comparison(wall, metrics, stats, loaded, pngs, cutouts_dir)
    print(f"WALL_CLOCK={wall:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
