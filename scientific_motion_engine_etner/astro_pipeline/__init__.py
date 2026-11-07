"""Motor científico SPHEREx. Entrada: Observation de Elide."""

from astro_pipeline._paths import ensure_imports

ensure_imports()

from astro_pipeline.align import align_observations_to_reference
from astro_pipeline.analyze import analyze_observations
from astro_pipeline.contracts import (
    AnalysisResult,
    Candidate,
    CandidateDetection,
    Observation,
    RejectionDiagnostics,
)
from astro_pipeline.load_fits import load_fits_region, load_spherex_observation
from astro_pipeline.visualize import visualize_candidates_on_image

__all__ = [
    "Observation",
    "Candidate",
    "CandidateDetection",
    "AnalysisResult",
    "RejectionDiagnostics",
    "analyze_observations",
    "align_observations_to_reference",
    "load_fits_region",
    "load_spherex_observation",
    "visualize_candidates_on_image",
]
