"""Compatibilidad: reexporta el API modular y el contrato Observation de Elide."""

from astro_pipeline._paths import ensure_imports

ensure_imports()

from astro_pipeline.analyze import analyze_observations
from astro_pipeline.contracts import AnalysisResult, Candidate, CandidateDetection, Observation
from astro_pipeline.load_fits import load_spherex_observation
from astro_pipeline.mock import create_mock_spherex_fits
from astro_pipeline.visualize import visualize_candidates_on_image

__all__ = [
    "Observation",
    "Candidate",
    "CandidateDetection",
    "AnalysisResult",
    "analyze_observations",
    "load_spherex_observation",
    "create_mock_spherex_fits",
    "visualize_candidates_on_image",
]


if __name__ == "__main__":
    from astro_pipeline.__main__ import main

    raise SystemExit(main())
