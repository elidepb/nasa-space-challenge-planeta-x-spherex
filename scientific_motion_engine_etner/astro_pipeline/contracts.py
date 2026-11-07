"""Contratos de salida del motor. La entrada es el Observation de Elide."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from astro_pipeline._paths import ensure_imports

ensure_imports()

from spherex_pipeline.models import Observation

__all__ = [
    "Observation",
    "CandidateDetection",
    "Candidate",
    "RejectionDiagnostics",
    "AnalysisResult",
]


@dataclass
class CandidateDetection:
    observationId: str
    timestamp: str
    ra: float
    dec: float
    x: float
    y: float
    snr: float | None = None


@dataclass
class Candidate:
    id: str
    ra: float
    dec: float
    displacementArcsec: float
    motionArcsecPerYear: float
    snr: float
    detections: list[CandidateDetection] = field(default_factory=list)
    status: str = "candidate"


@dataclass
class RejectionDiagnostics:
    """Por qué un par no llegó a `candidates`. No cambia el criterio de detección."""

    comparable_groups: int = 0
    epoch_pairs: int = 0
    peaks_positive: int = 0
    peaks_negative: int = 0
    pairs_below_min_step: int = 0
    pairs_above_max_step: int = 0
    pairs_flux_ratio: int = 0
    pairs_anti_star_veto: int = 0
    matched: int = 0
    snr_threshold: float = 6.0
    min_step_pixels: float = 1.3
    max_step_pixels: float = 8.0

    def merge(self, other: "RejectionDiagnostics") -> None:
        self.comparable_groups += other.comparable_groups
        self.epoch_pairs += other.epoch_pairs
        self.peaks_positive += other.peaks_positive
        self.peaks_negative += other.peaks_negative
        self.pairs_below_min_step += other.pairs_below_min_step
        self.pairs_above_max_step += other.pairs_above_max_step
        self.pairs_flux_ratio += other.pairs_flux_ratio
        self.pairs_anti_star_veto += other.pairs_anti_star_veto
        self.matched += other.matched


@dataclass
class AnalysisResult:
    candidates: list[Candidate]
    diagnostics: RejectionDiagnostics = field(default_factory=RejectionDiagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [asdict(candidate) for candidate in self.candidates],
            "diagnostics": asdict(self.diagnostics),
        }
