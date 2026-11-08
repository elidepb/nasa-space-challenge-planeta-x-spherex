"""Hermetic integration tests for the spectral analysis API (S13).

Elide and Etner are stubbed: no network, no real FITS downloads, no Etner
engine execution. The background Phase-2 task is replaced by a fake that
writes a fake PNG preview per record and marks the session COMPLETADO.
"""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from app.storage.factory import SessionRepositoryFactory
from app.routers import spectral_analysis as router_module

from main import app  # noqa: E402  (conftest already fixed sys.path)

client = TestClient(app)

IMAGES_DIR = Path("/tmp/backend_api_test_images")
CACHE_DIR = Path("/tmp/backend_api_test_cache")


def _make_fake_png(obs_id: str, images_dir: Path) -> Path:
    png_path = images_dir / f"{obs_id}.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color=(128, 128, 128)).save(png_path, format="PNG")
    return png_path


class _FakeObservation:
    def __init__(self, obs_id: str):
        self.id = obs_id
        self.image = np.full((32, 32), 100.0, dtype=np.float32)


_FAKE_RECORDS = [
    {
        "obs_id": "2025W20_1C_0373_1",
        "timestamp": "2025-05-14T09:07:24.651Z",
        "detector": 2,
        "wavelength": 1.2383,
        "bandwidth": 0.0334,
        "survey_index": 1,
        "fits_source": "/tmp/fake/2025W20_1C_0373_1.fits",
        "shape": [32, 32],
        "n_invalid_pixels": 0,
    },
    {
        "obs_id": "2025W49_2A_0756_3",
        "timestamp": "2025-12-07T11:25:51.120Z",
        "detector": 4,
        "wavelength": 1.45,
        "bandwidth": 0.0334,
        "survey_index": 2,
        "fits_source": "/tmp/fake/2025W49_2A_0756_3.fits",
        "shape": [32, 32],
        "n_invalid_pixels": 0,
    },
]


_FAKE_OBSERVATIONS = [_FakeObservation(r["obs_id"]) for r in _FAKE_RECORDS]


async def _fake_process_background_group(session_id, observations, images_dir):
    """Fake Phase 2: fake PNG per observation, mark COMPLETADO."""
    images_path = Path(images_dir)
    store = {}
    for obs in observations:
        obs_id = str(obs.id)
        _make_fake_png(obs_id, images_path)
        store[obs_id] = obs
    router_module._OBSERVATION_STORE[session_id] = store

    repo = SessionRepositoryFactory.get_repository()
    session = await repo.get_by_id(session_id)
    if session is None:
        session = {"session_id": session_id}
    session["estado"] = "COMPLETADO"
    session["progreso_porcentaje"] = 100.0
    session["observaciones_descargadas"] = len(observations)
    session["total_observaciones_grupo"] = len(observations)
    await repo.save(session)


def _fake_rgb_png(observations) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _clear_state():
    router_module._OBSERVATION_STORE.clear()
    repo = SessionRepositoryFactory.get_repository()
    try:
        repo._store.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


def _post_analysis(extra=None):
    payload = {
        "ra": 210.80227,
        "dec": 54.34895,
        "size_deg": 0.05,
        "bandpass": "SPHEREx-D2",
        "spectral_group": 5,
    }
    if extra:
        payload.update(extra)
    return client.post("/api/v1/spectral-analyses", json=payload)


def test_start_spectral_analysis_returns_202():
    _clear_state()
    with patch.object(
        router_module,
        "fetch_phase1_metadata_and_observations",
        return_value=(_FAKE_RECORDS, _FAKE_OBSERVATIONS),
    ), patch.object(
        router_module, "process_background_group", _fake_process_background_group
    ):
        response = _post_analysis()
    assert response.status_code == 202, response.text
    body = response.json()
    assert "session_id" in body
    assert body["estado"] == "EN_PROCESO"
    assert body["spectral_group"] == 5
    assert len(body["observaciones"]) == 2
    assert body["observaciones"][0]["id"] == "2025W20_1C_0373_1"


def test_polling_transitions_to_completado():
    _clear_state()
    with patch.object(
        router_module,
        "fetch_phase1_metadata_and_observations",
        return_value=(_FAKE_RECORDS, _FAKE_OBSERVATIONS),
    ), patch.object(router_module, "process_background_group", _fake_process_background_group):
        response = _post_analysis()
        session_id_value = response.json()["session_id"]
    response = client.get(f"/api/v1/spectral-analyses/{session_id_value}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estado"] == "COMPLETADO"
    assert body["progreso_porcentaje"] == 100.0
    assert body["observaciones_descargadas"] == 2


def test_preview_png_returns_image_with_cache_control():
    _clear_state()
    session_id_value = None
    with patch.object(
        router_module,
        "fetch_phase1_metadata_and_observations",
        return_value=(_FAKE_RECORDS[:1], _FAKE_OBSERVATIONS[:1]),
    ), patch.object(router_module, "process_background_group", _fake_process_background_group):
        response = _post_analysis()
        session_id_value = response.json()["session_id"]
    obs_id = _FAKE_RECORDS[0]["obs_id"]
    response = client.get(
        f"/api/v1/spectral-analyses/{session_id_value}/images/{obs_id}/preview.png"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert "max-age=86400" in response.headers.get("cache-control", "")
    assert response.content.startswith(b"\x89PNG")


def test_rgb_composite_returns_valid_png():
    _clear_state()
    session_id = uuid.uuid4()
    store = {
        "red_obs": _FakeObservation("red_obs"),
        "green_obs": _FakeObservation("green_obs"),
        "blue_obs": _FakeObservation("blue_obs"),
    }
    router_module._OBSERVATION_STORE[session_id] = store
    with patch.object(router_module, "generate_rgb_png", _fake_rgb_png):
        response = client.post(
            f"/api/v1/spectral-analyses/{session_id}/rgb-composite",
            json={
                "red_obs_id": "red_obs",
                "green_obs_id": "green_obs",
                "blue_obs_id": "blue_obs",
            },
        )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_factory_storage_type_switch():
    """T14: factory returns the right repository per STORAGE_TYPE, no router/service changes."""
    from app.storage.factory import SessionRepositoryFactory
    from app.storage.memory_repository import InMemorySessionRepository
    from app.storage.mongo_repository import MongoSessionRepository

    SessionRepositoryFactory._instance = None
    os.environ["STORAGE_TYPE"] = "memory"
    repo = SessionRepositoryFactory.get_repository()
    assert isinstance(repo, InMemorySessionRepository)

    SessionRepositoryFactory._instance = None
    os.environ["STORAGE_TYPE"] = "mongo"
    repo = SessionRepositoryFactory.get_repository()
    assert isinstance(repo, MongoSessionRepository)

    SessionRepositoryFactory._instance = None
    os.environ["STORAGE_TYPE"] = "memory"
