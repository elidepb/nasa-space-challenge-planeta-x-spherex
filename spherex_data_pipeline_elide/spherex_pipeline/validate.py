"""Comprobaciones de integridad sobre list[Observation]."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from astropy.time import Time

from spherex_pipeline.cutouts import wcs_contains_sky
from spherex_pipeline.irsa import extract_qr_from_url
from spherex_pipeline.models import Observation


@dataclass
class CheckResult:
    name: str
    passed: int
    total: int

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.passed == self.total

    def line(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return f"{self.name}: {self.passed}/{self.total} {status}"


def _finite_array(array: np.ndarray | None) -> bool:
    return array is not None and np.asarray(array).size > 0 and np.isfinite(array).any()


def contract_checks(observations: list[Observation]) -> dict[str, CheckResult]:
    n = len(observations)
    if n == 0:
        names = ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "valid_mask", "timestamp", "wavelength", "WCS")
        return {name: CheckResult(name, 0, 0) for name in names}

    image = CheckResult("IMAGE", sum(1 for o in observations if _finite_array(o.image)), n)
    flags = CheckResult(
        "FLAGS",
        sum(1 for o in observations if o.flags is not None and o.flags.shape == o.image.shape),
        n,
    )
    variance = CheckResult(
        "VARIANCE",
        sum(1 for o in observations if o.variance is not None and o.variance.shape == o.image.shape),
        n,
    )
    zodi = CheckResult(
        "ZODI",
        sum(1 for o in observations if o.zodi is not None and o.zodi.shape == o.image.shape),
        n,
    )
    mask = CheckResult(
        "valid_mask",
        sum(1 for o in observations if o.valid_mask is not None and o.valid_mask.shape == o.image.shape),
        n,
    )
    timestamp = CheckResult(
        "timestamp",
        sum(1 for o in observations if o.timestamp and o.timestamp != "unknown"),
        n,
    )
    wavelength = CheckResult(
        "wavelength",
        sum(1 for o in observations if o.wavelength is not None and np.isfinite(o.wavelength) and o.wavelength > 0),
        n,
    )
    wcs = CheckResult("WCS", sum(1 for o in observations if o.wcs() is not None), n)
    return {
        "IMAGE": image,
        "FLAGS": flags,
        "VARIANCE": variance,
        "ZODI": zodi,
        "valid_mask": mask,
        "timestamp": timestamp,
        "wavelength": wavelength,
        "WCS": wcs,
    }


def chronological_ok(observations: list[Observation]) -> tuple[bool, int, str, str]:
    if not observations:
        return True, 0, "", ""
    out_of_order = 0
    for left, right in zip(observations, observations[1:]):
        if left.timestamp > right.timestamp:
            out_of_order += 1
    return out_of_order == 0, out_of_order, observations[0].timestamp, observations[-1].timestamp


def duplicate_keys(observations: list[Observation]) -> list[tuple[str, str, str]]:
    counts = Counter(obs.product_key() for obs in observations)
    return [key for key, n in counts.items() if n > 1]


def qr_membership(observations: list[Observation], qr: str) -> tuple[int, int]:
    belong = 0
    other = 0
    for obs in observations:
        url = str(obs.metadata.get("access_url") or obs.fits_source)
        found = extract_qr_from_url(url)
        source = str(obs.metadata.get("source", ""))
        if source == "demo":
            if str(obs.metadata.get("qr")) == qr:
                belong += 1
            else:
                other += 1
            continue
        if found == qr:
            belong += 1
        else:
            other += 1
    return belong, other


def detector_membership(observations: list[Observation], bandpass: str) -> tuple[int, int]:
    expected = int(bandpass.rsplit("D", 1)[-1])
    match = 0
    other = 0
    for obs in observations:
        try:
            det = int(obs.detector)
        except (TypeError, ValueError):
            other += 1
            continue
        if det == expected:
            match += 1
        else:
            other += 1
    return match, other


def same_shape(observations: list[Observation]) -> bool:
    shapes = {obs.image.shape for obs in observations if obs.image is not None}
    return len(shapes) == 1


def target_inside_wcs(observations: list[Observation], ra: float, dec: float) -> int:
    return sum(1 for obs in observations if wcs_contains_sky(obs, ra, dec))


def timestamps_sortable(observations: list[Observation]) -> bool:
    try:
        Time([obs.timestamp for obs in observations], format="isot", scale="utc")
        return True
    except Exception:  # noqa: BLE001
        return False
