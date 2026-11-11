"""Pytest configuration: make sibling packages (Elide + Etner) importable."""

from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

# Point data volumes at local temp dirs BEFORE the app/settings are imported,
# so ensure_data_volumes() does not try to create /app/data (read-only outside Docker).
os.environ.setdefault("STORAGE_TYPE", "memory")
os.environ.setdefault("CACHE_DIR", str(Path(tempfile.gettempdir()) / "backend_api_test_cache"))
os.environ.setdefault("IMAGES_DIR", str(Path(tempfile.gettempdir()) / "backend_api_test_images"))

ROOT = Path(__file__).resolve().parents[1]          # .../backend_api_integration_anghelo

ROOT = Path(__file__).resolve().parents[1]          # .../backend_api_integration_anghelo
PROJECT_ROOT = ROOT.parent                           # .../nasa-space-challenge-planeta-x-spherex
BACKEND = ROOT

# Expose Elide (spherex_pipeline) and Etner (astro_pipeline) to the interpreter
# even when they are not pip-installed. The Dockerfile installs both editable,
# so this sys.path helper only matters for local test runs.
for _p in (PROJECT_ROOT / "spherex_data_pipeline_elide", PROJECT_ROOT / "scientific_motion_engine_etner"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

# Make the backend package importable from the repo root.
_backend_sp = str(BACKEND)
if _backend_sp not in sys.path:
    sys.path.insert(0, _backend_sp)

# Hermetic stub for reproject: astro_pipeline imports it for WCS alignment, but
# the tests stub out run_etner_analysis entirely, so reproject is never called.
if "reproject" not in sys.modules:
    _reproject_stub = types.ModuleType("reproject")
    _reproject_stub.reproject_interp = lambda *args, **kwargs: None
    sys.modules["reproject"] = _reproject_stub
