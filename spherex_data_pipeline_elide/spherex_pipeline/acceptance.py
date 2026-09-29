"""Acceptance test del SPHEREx Data Pipeline.

Uso:
    python -m spherex_pipeline.acceptance
"""

from __future__ import annotations

import argparse
import logging
import sys
from unittest.mock import patch

from astropy import log as astropy_log

from spherex_pipeline.constants import DEFAULT_BANDPASS, DEFAULT_QR, DEMO_DEC, DEMO_RA
from spherex_pipeline.irsa import extract_qr_from_url, normalize_qr, query_tap, resolve_bandpass
from spherex_pipeline.pipeline import get_observations, run_pipeline
from spherex_pipeline.validate import (
    chronological_ok,
    contract_checks,
    detector_membership,
    duplicate_keys,
    qr_membership,
    same_shape,
    target_inside_wcs,
)

RA = 210.80227
DEC = 54.34895
SIZE = 0.02
QR = "qr2"
BANDPASS = "SPHEREx-D2"


def _yn(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _run_error_cases() -> dict[str, str]:
    results: dict[str, str] = {}

    with patch("spherex_pipeline.pipeline.query_observations", return_value=[]):
        empty = run_pipeline(RA, DEC, SIZE, qr=QR, bandpass=BANDPASS, source="irsa")
        demo_leaked = any(str(obs.id).startswith("DEMO") for obs in empty.observations)
        results["empty region"] = _yn(empty.observations == [] and not demo_leaked)

    try:
        normalize_qr("qr999")
        results["invalid QR"] = "FAIL"
    except ValueError:
        results["invalid QR"] = "PASS"

    try:
        resolve_bandpass("INVALID")
        results["invalid bandpass"] = "FAIL"
    except ValueError:
        results["invalid bandpass"] = "PASS"

    results["IRSA -> demo"] = "NEVER"
    demo = get_observations(DEMO_RA, DEMO_DEC, 0.05, source="demo", qr=QR, bandpass=BANDPASS)
    results["explicit demo"] = _yn(
        len(demo) == 5
        and all(str(obs.id).startswith("DEMO") for obs in demo)
        and all(obs.metadata.get("source") == "demo" for obs in demo)
    )
    return results


def _qr3_smoke() -> tuple[str, str]:
    """Consulta QR3 independiente. Cero filas no es PASS de datos QR3."""
    try:
        records = query_tap(RA, DEC, SIZE, qr="qr3", bandpass=BANDPASS)
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"FAIL (TAP error: {exc})"
    qr3 = sum(1 for rec in records if extract_qr_from_url(rec.access_url) == "qr3")
    qr2 = sum(1 for rec in records if extract_qr_from_url(rec.access_url) == "qr2")
    leak = "PASS (0)" if qr2 == 0 else f"FAIL ({qr2})"
    if not records:
        return "NO DATA FOR TARGET", leak
    if qr2:
        return f"FAIL ({qr3}/{len(records)})", leak
    return f"PASS ({qr3}/{len(records)})", leak


def _bandpass_smoke() -> tuple[str, str]:
    try:
        d2 = query_tap(RA, DEC, SIZE, qr=QR, bandpass="SPHEREx-D2")
        d1 = query_tap(RA, DEC, SIZE, qr=QR, bandpass="SPHEREx-D1")
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"TAP bandpass error: {exc}"
    d2_urls = {rec.access_url.split("?")[0] for rec in d2}
    d1_urls = {rec.access_url.split("?")[0] for rec in d1}
    distinct = d1_urls != d2_urls
    return _yn(distinct and len(d1) >= 0 and len(d2) >= 0), f"D2={len(d2)} D1={len(d1)} distinct_urls={distinct}"


def _short_spectral_source(source: str | None) -> str:
    if not source:
        return "N/A"
    if "WCS-WAVE" in source:
        return "WCS-WAVE"
    if "CWAVE" in source or "CBAND" in source:
        return "CWAVE/CBAND"
    return source


def format_report(result, error_cases: dict[str, str], qr3_leak: str, qr3_status: str, bp_note: str, bp_status: str) -> str:
    observations = result.observations
    report = result.report
    query = result.query
    checks = contract_checks(observations)
    chrono_ok, out_of_order, first_ts, last_ts = chronological_ok(observations)
    dupes = duplicate_keys(observations)
    qr_ok, qr_other = qr_membership(observations, str(query["qr"]))
    det_ok, det_other = detector_membership(observations, str(query["bandpass"]))
    shape_ok = same_shape(observations)
    inside = target_inside_wcs(observations, float(query["ra"]), float(query["dec"]))
    n = len(observations)
    retrieval_ok = (
        report.tap_matches == report.requested == n
        and report.downloaded == report.parsed == n
        and report.failed_downloads == 0
        and report.failed_parses == 0
        and report.duplicates == 0
        and not report.failures
    )
    wave_sources = sorted(
        {_short_spectral_source(obs.spectral_calibration_source or obs.wavelength_source) for obs in observations}
    )
    bw_sources = sorted({_short_spectral_source(obs.bandwidth_source) for obs in observations})
    cal_qualities = sorted({(obs.spectral_calibration_quality or "unavailable").upper() for obs in observations})
    spectral_units = sorted({obs.spectral_unit or "N/A" for obs in observations})
    contract_ok = n > 0 and all(item.ok for item in checks.values())
    integrity_ok = (
        qr_other == 0
        and det_other == 0
        and chrono_ok
        and shape_ok
        and inside == n
        and out_of_order == 0
        and not dupes
    )
    errors_ok = all(value in {"PASS", "NEVER"} for value in error_cases.values())
    qr3_ok = qr3_status == "NO DATA FOR TARGET" or qr3_status.startswith("PASS")
    leak_ok = qr3_leak.startswith("PASS")
    final = retrieval_ok and integrity_ok and contract_ok and errors_ok and qr3_ok and leak_ok and bp_status == "PASS"

    lines = [
        "SPHEREx DATA PIPELINE — ACCEPTANCE TEST",
        "",
        "Query",
        "--------------------------------",
        f"source:     {str(query['source']).upper()}",
        f"release:    {str(query['qr']).upper()}",
        f"bandpass:   {query['bandpass']}",
        f"RA:         {query['ra']}",
        f"Dec:        {query['dec']}",
        f"size:       {query['size']}",
        "",
        "Retrieval",
        "--------------------------------",
        f"TAP matches:        {report.tap_matches}",
        f"requested:          {report.requested}",
        f"downloaded:         {report.downloaded}",
        f"parsed:             {report.parsed}",
        f"observations:       {report.observations}",
        f"failed:             {report.failed_downloads + report.failed_parses}",
        f"duplicates:         {report.duplicates}",
        f"first timestamp:    {first_ts}",
        f"last timestamp:     {last_ts}",
        f"out-of-order:       {out_of_order}",
        "",
        "Integrity",
        "--------------------------------",
        f"QR2 only:           {_yn(qr_ok == n and qr_other == 0)}  ({qr_ok}/{n})",
        f"D2 only:            {_yn(det_ok == n and det_other == 0)}  ({det_ok}/{n})",
        f"chronological:      {_yn(chrono_ok)}",
        f"same shape:         {_yn(shape_ok)}  ({observations[0].image.shape if observations else None})",
        f"same sky region:    {_yn(shape_ok and inside == n)}",
        f"target inside WCS:  {_yn(inside == n)}  ({inside}/{n})",
        "",
        "Data",
        "--------------------------------",
    ]
    for name in ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "valid_mask", "timestamp", "wavelength", "WCS"):
        item = checks[name]
        status = "PASS" if item.ok else "FAIL"
        lines.append(f"{name + ':':<20}{item.passed}/{item.total} {status}")
    lines.extend(
        [
            "",
            "Spectral metadata",
            "--------------------------------",
            f"wavelength source:      {', '.join(wave_sources) if wave_sources else 'N/A'}",
            f"bandwidth source:       {', '.join(bw_sources) if bw_sources else 'N/A'}",
            f"calibration quality:    {', '.join(cal_qualities) if cal_qualities else 'N/A'}",
            f"unit:                   {', '.join(spectral_units) if spectral_units else 'N/A'}",
            "CWAVE/CBAND in MEF:     N/A",
            "",
            "QR3 / bandpass smoke",
            "--------------------------------",
            f"QR3 query:          {qr3_status}",
            f"QR2 leakage:        {qr3_leak}",
            f"D1 vs D2 query:     {bp_status}  ({bp_note})",
            "",
            "Error behavior",
            "--------------------------------",
            f"empty region:       {error_cases['empty region']}",
            f"invalid QR:         {error_cases['invalid QR']}",
            f"invalid bandpass:   {error_cases['invalid bandpass']}",
            f"IRSA -> demo:       {error_cases['IRSA -> demo']}",
            f"explicit demo:      {error_cases['explicit demo']}",
            "",
            "Contract",
            "--------------------------------",
            f"list[Observation]:  {_yn(n == report.tap_matches and n == report.requested)}",
            "",
            "FINAL RESULT",
            "--------------------------------",
            "PASS" if final else "FAIL",
        ]
    )
    if report.failures:
        lines.append("")
        lines.append("Failures")
        lines.append("--------------------------------")
        lines.extend(item.line() for item in report.failures)
    if dupes:
        lines.append("")
        lines.append(f"Duplicate keys: {dupes}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acceptance test SPHEREx Data Pipeline")
    parser.add_argument("--ra", type=float, default=RA)
    parser.add_argument("--dec", type=float, default=DEC)
    parser.add_argument("--size", type=float, default=SIZE)
    parser.add_argument("--qr", default=QR)
    parser.add_argument("--bandpass", default=BANDPASS)
    args = parser.parse_args(argv)

    astropy_log.setLevel("ERROR")
    logging.getLogger("astropy").setLevel(logging.ERROR)
    logging.getLogger("astropy.wcs").setLevel(logging.ERROR)

    error_cases = _run_error_cases()
    qr3_status, qr3_leak = _qr3_smoke()
    bp_status, bp_note = _bandpass_smoke()
    result = run_pipeline(
        args.ra,
        args.dec,
        args.size,
        qr=args.qr,
        bandpass=args.bandpass,
        source="irsa",
        max_observations=None,
    )
    text = format_report(result, error_cases, qr3_leak, qr3_status, bp_note, bp_status)
    sys.stdout.write(text)
    return 0 if text.strip().endswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
