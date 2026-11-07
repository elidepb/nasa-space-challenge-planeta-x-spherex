"""Baja los campos del desafío NASA con defaults de Elide y corre el motor."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from astro_pipeline.analyze import analyze_observations
from astro_pipeline.pair_wavelength import group_comparable_epochs
from astro_pipeline.read_observation import ensure_spatial_wcs
from spherex_pipeline.pipeline import get_observations

SIZE_DEG = 0.05
TARGETS = [
    {
        "name": "WISE 0855",
        "ra": 133.795129,
        "dec": -7.245147,
        "why": "enana marrón de movimiento propio alto (primer test del enunciado)",
    },
    {
        "name": "Barnard's Star",
        "ra": 269.452076,
        "dec": 4.693391,
        "why": "estrella con el mayor movimiento propio conocido",
    },
    {
        "name": "Epsilon Indi B",
        "ra": 331.043833,
        "dec": -56.782694,
        "why": "par de enanas marrones alrededor de Epsilon Indi",
    },
    {
        "name": "RW Aurigae",
        "ra": 76.956417,
        "dec": 30.401408,
        "why": "estrella variable (cambio de brillo, no de posición)",
    },
    {
        "name": "R Draconis",
        "ra": 248.167625,
        "dec": 66.754444,
        "why": "estrella variable (cambio de brillo, no de posición)",
    },
]


def _epoch_summary(obs) -> dict:
    shape = None if obs.image is None else list(obs.image.shape)
    n_valid = None if obs.valid_mask is None else int(obs.valid_mask.sum())
    n_pix = None if obs.valid_mask is None else int(obs.valid_mask.size)
    return {
        "id": obs.id,
        "timestamp": obs.timestamp,
        "wavelength": None if obs.wavelength is None else float(obs.wavelength),
        "bandwidth": None if obs.bandwidth is None else float(obs.bandwidth),
        "detector": obs.detector,
        "shape": shape,
        "n_valid_pixels": n_valid,
        "n_pixels": n_pix,
        "has_wcs": obs.wcs() is not None,
        "has_zodi": obs.zodi is not None,
        "has_variance": obs.variance is not None,
    }


def probe_one(target: dict) -> dict:
    print(f"\n=== {target['name']} ra={target['ra']} dec={target['dec']} ===", flush=True)
    row = {
        "name": target["name"],
        "ra": target["ra"],
        "dec": target["dec"],
        "why": target["why"],
        "query": {
            "size": SIZE_DEG,
            "qr": "qr2",
            "bandpass": "SPHEREx-D2",
            "method": "spectral",
            "group": 7,
            "source": "irsa",
        },
        "ok": False,
        "n_observations": 0,
        "epochs": [],
        "n_comparable_groups": 0,
        "n_candidates": 0,
        "candidates": [],
        "error": None,
    }
    try:
        observations = get_observations(target["ra"], target["dec"], SIZE_DEG)
        observations = [ensure_spatial_wcs(obs) for obs in observations]
        row["n_observations"] = len(observations)
        row["epochs"] = [_epoch_summary(obs) for obs in observations]
        groups = group_comparable_epochs(observations)
        row["n_comparable_groups"] = len(groups)
        print(
            f"  observaciones={len(observations)} grupos_comparables={len(groups)}",
            flush=True,
        )
        if len(observations) >= 2:
            result = analyze_observations(observations)
            row["candidates"] = result.get("candidates", [])
            row["n_candidates"] = len(row["candidates"])
        row["ok"] = True
        print(f"  candidatos={row['n_candidates']}", flush=True)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc()
        print(f"  ERROR {row['error']}", flush=True)
    return row


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    results = [probe_one(target) for target in TARGETS]
    payload = {
        "size_deg": SIZE_DEG,
        "defaults": "Elide get_observations: qr2, SPHEREx-D2, method=spectral, group=7",
        "targets": results,
    }
    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nResumen escrito en {out_path}", flush=True)
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
