"""El filtro 1.3–8 px y los vetos, con picos conocidos (sin el resto del pipeline)."""

import numpy as np

from astro_pipeline.match_dipoles import match_moving_dipoles


def _blank(n: int = 40) -> np.ndarray:
    return np.zeros((n, n), dtype=float)


def test_accepts_dipole_inside_default_window():
    pos = [{"x": 20.0, "y": 18.0, "snr": 10.0}]
    neg = [{"x": 17.0, "y": 18.0, "snr": 10.0}]
    matches, diag = match_moving_dipoles(pos, neg, _blank(), _blank())
    assert len(matches) == 1
    assert 2.9 < matches[0].dist_pix < 3.1
    assert diag.matched == 1
    assert diag.pairs_below_min_step == 0
    assert diag.pairs_above_max_step == 0


def test_rejects_shift_below_min_step():
    pos = [{"x": 20.9, "y": 18.0, "snr": 10.0}]
    neg = [{"x": 20.0, "y": 18.0, "snr": 10.0}]
    matches, diag = match_moving_dipoles(pos, neg, _blank(), _blank())
    assert matches == []
    assert diag.pairs_below_min_step == 1
    assert diag.matched == 0


def test_rejects_shift_above_max_step():
    pos = [{"x": 38.0, "y": 18.0, "snr": 10.0}]
    neg = [{"x": 18.0, "y": 18.0, "snr": 10.0}]
    matches, diag = match_moving_dipoles(pos, neg, _blank(), _blank())
    assert matches == []
    assert diag.pairs_above_max_step == 1
    assert diag.matched == 0


def test_rejects_inconsistent_flux_ratio():
    pos = [{"x": 20.0, "y": 18.0, "snr": 20.0}]
    neg = [{"x": 17.0, "y": 18.0, "snr": 5.0}]
    matches, diag = match_moving_dipoles(pos, neg, _blank(), _blank())
    assert matches == []
    assert diag.pairs_flux_ratio == 1


def test_vetoes_fixed_star_residual():
    pos = [{"x": 20.0, "y": 18.0, "snr": 10.0}]
    neg = [{"x": 17.0, "y": 18.0, "snr": 10.0}]
    image_t1 = _blank()
    image_t2 = _blank()
    image_t2[18, 17] = 10.0
    matches, diag = match_moving_dipoles(pos, neg, image_t1, image_t2)
    assert matches == []
    assert diag.pairs_anti_star_veto == 1


def test_opt_in_min_step_does_not_change_default():
    pos = [{"x": 20.9, "y": 18.0, "snr": 10.0}]
    neg = [{"x": 20.0, "y": 18.0, "snr": 10.0}]
    default, _ = match_moving_dipoles(pos, neg, _blank(), _blank())
    lowered, _ = match_moving_dipoles(
        pos, neg, _blank(), _blank(), min_step_pixels=0.5
    )
    assert default == []
    assert len(lowered) == 1
