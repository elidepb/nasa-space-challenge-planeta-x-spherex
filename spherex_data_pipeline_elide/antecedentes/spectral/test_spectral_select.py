"""El CLI paralelo no debe romper el extractor original."""

from spherex_pipeline.pipeline import get_observations
from spherex_pipeline.spectral_select import get_detector_bins, main


def test_pipeline_entry_still_exports_get_observations():
    assert callable(get_observations)


def test_detector_bins_cover_d2():
    bins = get_detector_bins("SPHEREx-D2", n_bins=17)
    assert len(bins) == 17
    assert bins[0]["wl_min"] == 1.088
    assert bins[-1]["wl_max"] == 1.656


def test_demo_source_runs_without_network(tmp_path):
    code = main(
        [
            "--source",
            "demo",
            "--group",
            "1",
            "--images-dir",
            str(tmp_path / "png"),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    assert code == 0
    pngs = list((tmp_path / "png").glob("*.png"))
    assert pngs
