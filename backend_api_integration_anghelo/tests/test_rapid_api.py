"""Integration tests for SPHEREx rapid in-memory analysis endpoints."""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure backend and siblings are in sys.path
_TEST_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _TEST_DIR.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_BACKEND_DIR, _PROJECT_ROOT / "spherex_data_pipeline_elide", _PROJECT_ROOT / "scientific_motion_engine_etner"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from main import app  # noqa: E402

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] == "in-memory-temporal-median"


def test_sed_endpoint():
    response = client.get("/api/v1/sed?ra=133.7862&dec=-7.2443")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 102
    assert "um" in data[0]
    assert "mjy" in data[0]
    assert data[0]["um"] == 0.75
    assert data[-1]["um"] == 5.0


def test_analyze_endpoint():
    response = client.get("/api/v1/analyze?ra=7.9377&dec=-10.97988&size=180&band=D5&source=demo")
    assert response.status_code == 200
    data = response.json()
    assert "ra" in data
    assert "dec" in data
    assert "epochs" in data
    assert "candidates" in data
    assert len(data["epochs"]) >= 2
    first = data["epochs"][0]
    assert "original_png" in first
    assert "residual_png" in first
    assert first["original_png"].startswith("data:image/png;base64,")
    assert first["residual_png"].startswith("data:image/png;base64,")
    assert len(data["candidates"]) >= 1
