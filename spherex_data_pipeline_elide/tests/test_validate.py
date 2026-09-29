"""Tests de homogeneidad, duplicados y contrato demo."""

from spherex_pipeline.constants import DEMO_DEC, DEMO_RA, DEMO_SIZE_DEG
from spherex_pipeline.cutouts import wcs_contains_sky
from spherex_pipeline.irsa import IrsaRecord, dedupe_records, extract_qr_from_url
from spherex_pipeline.pipeline import get_observations
from spherex_pipeline.validate import chronological_ok, contract_checks, duplicate_keys


def test_demo_contract_wcs_and_no_duplicates(tmp_path):
    observations = get_observations(
        DEMO_RA,
        DEMO_DEC,
        DEMO_SIZE_DEG,
        source="demo",
        qr="qr2",
        bandpass="SPHEREx-D2",
        demo_dir=tmp_path,
    )
    assert len(observations) == 5
    chrono_ok, out_of_order, _, _ = chronological_ok(observations)
    assert chrono_ok
    assert out_of_order == 0
    assert duplicate_keys(observations) == []
    assert len({obs.image.shape for obs in observations}) == 1
    assert all(wcs_contains_sky(obs, DEMO_RA, DEMO_DEC) for obs in observations)
    checks = contract_checks(observations)
    assert all(item.ok for item in checks.values())
    assert all(obs.flags.shape == obs.image.shape for obs in observations)
    assert all(obs.variance.shape == obs.image.shape for obs in observations)
    assert all(obs.zodi.shape == obs.image.shape for obs in observations)
    assert all(obs.wavelength > 0 for obs in observations)
    assert all(obs.bandwidth is None or obs.bandwidth > 0 for obs in observations)


def test_extract_qr_from_real_url():
    qr2 = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/file.fits"
    qr3 = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/file.fits"
    assert extract_qr_from_url(qr2) == "qr2"
    assert extract_qr_from_url(qr3) == "qr3"


def test_dedupe_records_counts_duplicates():
    records = [
        IrsaRecord(access_url="a.fits", cutout_url="a.fits?x=1", time_mjd=1.0, bandpass="SPHEREx-D2"),
        IrsaRecord(access_url="a.fits", cutout_url="a.fits?x=1", time_mjd=1.0, bandpass="SPHEREx-D2"),
        IrsaRecord(access_url="b.fits", cutout_url="b.fits?x=1", time_mjd=2.0, bandpass="SPHEREx-D2"),
    ]
    unique, n_dupes = dedupe_records(records)
    assert len(unique) == 2
    assert n_dupes == 1
