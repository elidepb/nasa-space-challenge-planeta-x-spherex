"""CLI: consume get_observations de Elide y corre el motor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astro_pipeline._paths import ensure_imports

ensure_imports()

from astro_pipeline.analyze import analyze_observations
from astro_pipeline.load_fits import load_spherex_observation
from astro_pipeline.mock import mock_observations
from astro_pipeline.visualize import visualize_candidates_on_image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Motor SPHEREx: imprime el JSON que Anghelo consume en /candidates."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa observaciones sintéticas (con y sin movimiento) y muestra el handoff JSON.",
    )
    args = parser.parse_args(argv)
    if args.mock:
        return _print_mock_handoff()
    return _run_elide_or_fits()


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


def _run_elide_or_fits() -> int:
    observations = _load_from_elide_demo()
    if observations is None:
        observations = _load_local_fits()
    if observations is None or len(observations) < 2:
        raise FileNotFoundError(
            "Se necesitan al menos 2 Observation. Instala spherex_pipeline "
            "o coloca FITS level2_ en scientific_motion_engine_etner/spherex_6_bandas. "
            "Para ver el JSON de handoff sin FITS: python -m astro_pipeline --mock"
        )

    print(f"Observaciones Elide: {len(observations)}")
    for obs in observations:
        print(
            f" -> {obs.id}  t={obs.timestamp}  λ={obs.wavelength}  "
            f"detector={obs.detector}  shape={None if obs.image is None else obs.image.shape}"
        )

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


def _load_local_fits():
    folder = Path(__file__).resolve().parents[1] / "spherex_6_bandas"
    if not folder.is_dir():
        return None
    files = sorted(path for path in folder.iterdir() if path.is_file() and "level2_" in path.name)
    if len(files) < 2:
        return None
    return [load_spherex_observation(path) for path in files]


if __name__ == "__main__":
    raise SystemExit(main())
