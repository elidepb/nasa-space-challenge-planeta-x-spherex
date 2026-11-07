"""Regresión: los campos del desafío NASA no deben reportar dipolos 1.3–8 px."""

import json
from pathlib import Path

SUMMARY = Path(__file__).resolve().parents[1] / "challenge_targets" / "summary.json"


def test_challenge_fields_reported_zero_dipole_candidates():
    payload = json.loads(SUMMARY.read_text())
    assert payload["targets"], "el probe debió dejar al menos un objetivo"
    for target in payload["targets"]:
        assert target["n_candidates"] == 0, (
            f"{target['name']} no debe entrar a candidates "
            f"(el dipolo 1.3–8 px no aplica a estos campos)"
        )
        assert target["candidates"] == []
