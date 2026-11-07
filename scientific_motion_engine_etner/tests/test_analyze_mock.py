from astro_pipeline.analyze import analyze_observations
from astro_pipeline.mock import inject_moving_source, mock_observations
from astro_pipeline.pair_wavelength import group_comparable_epochs, pair_comparable_epochs
from spherex_pipeline.models import Observation

PLATE_SCALE_ARCSEC = 6.15


def test_analyze_observations_uses_elide_contract_and_finds_motion():
    observations = mock_observations()
    assert all(hasattr(obs, "image") for obs in observations)
    assert all(obs.wcs() is not None for obs in observations)
    assert all(obs.valid_mask is not None for obs in observations)

    result = analyze_observations(observations, snr_threshold=6.0)
    candidates = result["candidates"]
    assert candidates, "el dipolo sintético debería producir al menos un candidato"
    first = candidates[0]
    assert first["id"].startswith("C-")
    assert first["status"] == "candidate"
    assert len(first["detections"]) == 2
    assert first["detections"][0]["observationId"] == "MOCK-T1"
    assert first["detections"][1]["observationId"] == "MOCK-T2"
    assert first["displacementArcsec"] > 0
    assert first["snr"] >= 6.0
    dx = first["detections"][1]["x"] - first["detections"][0]["x"]
    assert abs(dx - 3.0) < 0.6
    assert abs(first["displacementArcsec"] - 3.0 * PLATE_SCALE_ARCSEC) < 4.0
    assert result["diagnostics"]["matched"] == len(candidates)
    assert result["diagnostics"]["min_step_pixels"] == 1.3
    assert result["diagnostics"]["max_step_pixels"] == 8.0


def test_engine_consumes_elide_observation_class():
    observations = mock_observations()
    assert all(isinstance(obs, Observation) for obs in observations)
    assert all(obs.__class__.__module__ == "spherex_pipeline.models" for obs in observations)


def test_group_aligns_all_epochs_to_one_channel():
    observations = mock_observations()
    groups = group_comparable_epochs(observations)
    assert len(groups) == 1
    assert [obs.id for obs in groups[0]] == ["MOCK-T1", "MOCK-T2"]


def test_pair_comparable_epochs_splits_different_wavelengths():
    observations = mock_observations()
    observations[1].wavelength = 4.8
    pairs = pair_comparable_epochs(observations, max_delta_um=0.05)
    assert pairs == []


def test_no_motion_static_field_has_zero_candidates():
    result = analyze_observations(mock_observations(include_mover=False))
    diag = result["diagnostics"]
    assert result["candidates"] == []
    assert diag["comparable_groups"] == 1
    assert diag["peaks_positive"] == 0
    assert diag["peaks_negative"] == 0
    assert diag["matched"] == 0


def test_subpixel_shift_is_seen_and_rejected():
    """0.9 px (régimen Barnard's): hay dipolo, no entra a candidates."""
    result = analyze_observations(mock_observations(shift_xy=(0.9, 0.0)))
    diag = result["diagnostics"]
    assert result["candidates"] == []
    assert diag["peaks_positive"] >= 1
    assert diag["peaks_negative"] >= 1
    assert diag["pairs_below_min_step"] + diag["pairs_anti_star_veto"] >= 1
    assert diag["matched"] == 0


def test_above_max_step_is_seen_and_rejected():
    """20 px (régimen Ceres): hay dipolo, queda fuera de 8 px."""
    result = analyze_observations(mock_observations(shift_xy=(20.0, 0.0)))
    diag = result["diagnostics"]
    assert result["candidates"] == []
    assert diag["peaks_positive"] >= 1
    assert diag["peaks_negative"] >= 1
    assert diag["pairs_above_max_step"] >= 1
    assert diag["matched"] == 0


def test_single_epoch_has_zero_candidates():
    result = analyze_observations(mock_observations()[:1])
    assert result["candidates"] == []
    assert result["diagnostics"]["comparable_groups"] == 0
    assert result["diagnostics"]["epoch_pairs"] == 0


def test_different_wavelength_has_zero_candidates():
    result = analyze_observations(mock_observations(t2_wavelength=4.8))
    assert result["candidates"] == []
    assert result["diagnostics"]["comparable_groups"] == 0


def test_planted_mover_is_recovered_without_telling_the_engine():
    static = mock_observations(include_mover=False)
    planted = inject_moving_source(static, xy=(80.0, 60.0), shift_xy=(3.0, 0.0))
    result = analyze_observations(planted)
    assert result["candidates"], "el motor debe recuperar el móvil plantado"
    first = result["candidates"][0]
    dx = first["detections"][1]["x"] - first["detections"][0]["x"]
    assert abs(dx - 3.0) < 0.6
    assert abs(first["detections"][0]["x"] - 80.0) < 1.0
    assert abs(first["detections"][0]["y"] - 60.0) < 1.0
