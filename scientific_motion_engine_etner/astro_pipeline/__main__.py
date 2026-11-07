"""CLI: consume get_observations de Elide y corre el motor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astro_pipeline._paths import ensure_imports

ensure_imports()

from astro_pipeline.align import align_observations_to_reference
from astro_pipeline.analyze import analyze_observations
from astro_pipeline.load_fits import load_fits_region, load_spherex_observation
from astro_pipeline.mock import mock_observations
from astro_pipeline.visualize import visualize_candidates_on_image

LOCAL_FITS_DIR = Path(__file__).resolve().parents[1] / "spherex_6_bandas"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Motor SPHEREx: imprime el JSON que Anghelo consume en /candidates."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa observaciones sintéticas (con y sin movimiento) y muestra el handoff JSON.",
    )
    parser.add_argument(
        "--fits",
        nargs="+",
        default=None,
        help="FITS crudos (Level-2/4). Se recortan a un cuadrado común antes de comparar.",
    )
    parser.add_argument("--ra", type=float, default=None, help="Centro RA del recorte (grados).")
    parser.add_argument("--dec", type=float, default=None, help="Centro Dec del recorte (grados).")
    parser.add_argument(
        "--size",
        type=float,
        default=None,
        help="Lado del recorte en grados (ej. 0.85). Si se omite, se estima del FITS.",
    )
    args = parser.parse_args(argv)
    if args.mock:
        return _print_mock_handoff()
    return _run_elide_or_fits(args)


def _print_mock_handoff() -> int:
    """Muestra entrada (resumen Elide) y el cuerpo JSON para Anghelo."""
    cases = [
        (
            "CON movimiento (dipolo 3 px, dentro de 1.3–8 px)",
            mock_observations(shift_xy=(3.0, 0.0)),
        ),
        (
            "SIN movimiento (solo estrella fija)",
            mock_observations(include_mover=False),
        ),
    ]
    for title, observations in cases:
        print("=" * 72)
        print(title)
        print("=" * 72)
        print("\n--- Entrada: Observation.to_summary() (Elide → Etner) ---")
        print(json.dumps([obs.to_summary() for obs in observations], indent=2))
        result = analyze_observations(observations)
        print("\n--- GET /analysis/{id}/candidates  (Etner → Anghelo) ---")
        print(json.dumps(result["candidates"], indent=2))
        print("\n--- AnalysisResult completo del motor (candidates + diagnostics) ---")
        print(json.dumps(result, indent=2))
        print()
    return 0


def _run_elide_or_fits(args: argparse.Namespace) -> int:
    observations = None
    if args.fits:
        observations = _load_raw_fits(args.fits, ra=args.ra, dec=args.dec, size=args.size)
    if observations is None:
        observations = _load_local_fits(ra=args.ra, dec=args.dec, size=args.size)
    if observations is None:
        observations = _load_from_elide_demo()
    if observations is None or len(observations) < 2:
        raise FileNotFoundError(
            "Se necesitan al menos 2 Observation. Pasa --fits a.fits b.fits, "
            "coloca FITS en scientific_motion_engine_etner/spherex_6_bandas, "
            "o usa: python -m astro_pipeline --mock"
        )

    print(f"Observaciones: {len(observations)}")
    for obs in observations:
        print(
            f" -> {obs.id}  t={obs.timestamp}  λ={obs.wavelength}  "
            f"detector={obs.detector}  shape={None if obs.image is None else obs.image.shape}"
        )
    shapes = {None if obs.image is None else tuple(obs.image.shape) for obs in observations}
    if len(shapes) == 1:
        print(f"Grilla común para comparar/restar: {next(iter(shapes))}")
    else:
        print(f"[aviso] shapes aún distintos: {shapes}")

    result = analyze_observations(observations)
    print("\n--- GET /analysis/{id}/candidates  (Etner → Anghelo) ---")
    print(json.dumps(result["candidates"], indent=2))
    print("\n--- AnalysisResult completo del motor ---")
    print(json.dumps(result, indent=2))

    candidates = result.get("candidates", [])
    if candidates:
        output_file = str(Path(__file__).resolve().parent / "candidates_marked.png")
        visualize_candidates_on_image(
            observation=observations[0],
            candidates=candidates,
            output_path=output_file,
            show_plot=False,
        )
    else:
        print("\n[!] No se encontraron candidatos para visualizar.")
    return 0


def _load_from_elide_demo():
    try:
        from spherex_pipeline import get_observations
        from spherex_pipeline.constants import DEMO_DEC, DEMO_RA
    except ImportError:
        return None
    try:
        observations = get_observations(
            DEMO_RA,
            DEMO_DEC,
            0.05,
            source="demo",
            qr="qr2",
            bandpass="SPHEREx-D2",
        )
    except Exception as exc:
        print(f"[aviso] No se pudo usar get_observations(source='demo'): {exc}")
        return None
    if len(observations) < 2:
        return None
    return observations


def _load_raw_fits(
    fits_paths: list[str | Path],
    *,
    ra: float | None,
    dec: float | None,
    size: float | None,
):
    paths = [Path(path) for path in fits_paths]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"No existen: {missing}")
    return _harmonize_fits(paths, ra=ra, dec=dec, size=size)


def _load_local_fits(
    *,
    ra: float | None = None,
    dec: float | None = None,
    size: float | None = None,
):
    if not LOCAL_FITS_DIR.is_dir():
        return None
    files = sorted(
        path
        for path in LOCAL_FITS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".fits", ".fit", ".fz"}
    )
    if len(files) < 2:
        return None
    print(f"FITS locales en {LOCAL_FITS_DIR.name}: {len(files)}")
    return _harmonize_fits(files, ra=ra, dec=dec, size=size)


def _harmonize_fits(
    paths: list[Path],
    *,
    ra: float | None,
    dec: float | None,
    size: float | None,
):
    native = [load_spherex_observation(path) for path in paths]
    print("Shapes nativos (FITS crudos):")
    for obs, path in zip(native, paths):
        print(f"  {path.name}: {obs.image.shape}")

    ra, dec, size = _region_for_fits(native, ra=ra, dec=dec, size=size)
    print(f"Recorte común: ra={ra} dec={dec} size={size}°")
    prepared = load_fits_region(paths, ra, dec, size)
    prepared = align_observations_to_reference(prepared)
    print("Shapes tras armonizar (comparables):")
    for obs in prepared:
        print(f"  {obs.id}: {obs.image.shape}")
    return prepared


def _region_for_fits(observations, *, ra, dec, size):
    try:
        from spherex_pipeline.constants import DEMO_DEC, DEMO_RA
    except ImportError:
        DEMO_RA, DEMO_DEC = 210.80227, 54.34895
    if ra is None:
        ra = float(DEMO_RA)
    if dec is None:
        dec = float(DEMO_DEC)
    if size is None:
        size = _estimate_size_deg(observations)
    return float(ra), float(dec), float(size)


def _estimate_size_deg(observations) -> float:
    from astropy.wcs.utils import proj_plane_pixel_scales

    sides = []
    for obs in observations:
        wcs = obs.wcs()
        if wcs is None or obs.image is None:
            continue
        scales = proj_plane_pixel_scales(wcs)
        ny, nx = obs.image.shape[-2:]
        sides.append(float(min(nx * scales[0], ny * scales[1])))
    if not sides:
        return 0.05
    return round(min(sides), 4)


if __name__ == "__main__":
    raise SystemExit(main())
