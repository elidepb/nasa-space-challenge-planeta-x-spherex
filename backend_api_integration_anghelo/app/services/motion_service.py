"""Phase 3 motion service: bridge to the Etner scientific engine.

The router keeps the ready group of observations in memory (Elide contract) and
delegates the CPU-bound candidate search to Etner. This module stays thin on
purpose: it owns no thresholds, no downloads and no persistence, so the
scientific contract remains in ``astro_pipeline`` and can evolve without
touching the API layer.
"""

from __future__ import annotations

from typing import Any

from astro_pipeline.analyze import analyze_observations
from astro_pipeline.contracts import AnalysisResult
from spherex_pipeline.models import Observation

# Displacement is measured between epochs, so the engine needs at least two.
_MIN_OBSERVATIONS = 2


def run_etner_analysis(observations: list[Observation]) -> dict[str, Any]:
    """Run the Etner engine over one ready group of observations.

    The caller passes the frames already loaded in memory, so this function
    performs no I/O and no download. It is synchronous because the engine is
    CPU-bound; the router must offload it with ``asyncio.to_thread``.

    Args:
        observations: Frames of a single spectral group, already in memory.

    Returns:
        The engine result with a ``candidates`` list and a ``diagnostics``
        dict. When fewer than two frames are available there is nothing to
        compare across epochs, so an empty, well-formed result is returned
        instead of raising.
    """
    if len(observations) < _MIN_OBSERVATIONS:
        # Reuse the engine's own result contract so the empty payload keeps the
        # exact diagnostics shape and defaults instead of drifting from it.
        return AnalysisResult(candidates=[]).to_dict()

    return analyze_observations(observations)
