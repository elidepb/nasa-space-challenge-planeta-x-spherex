"""Pipeline de datos SPHEREx (Elide)."""

from spherex_pipeline.models import Observation
from spherex_pipeline.pipeline import get_observations, run_pipeline

__all__ = ["Observation", "get_observations", "run_pipeline"]
__version__ = "0.1.0"
