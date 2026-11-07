"""Añade al path el motor y el pipeline de Elide (contrato Observation)."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
ELIDE_ROOT = REPO_ROOT / "spherex_data_pipeline_elide"


def ensure_imports() -> None:
    for path in (ENGINE_ROOT, ELIDE_ROOT):
        text = str(path)
        if path.is_dir() and text not in sys.path:
            sys.path.insert(0, text)
