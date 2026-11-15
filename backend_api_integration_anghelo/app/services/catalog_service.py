"""Phase 1 catalog service: metadata-only retrieval through the Elide pipeline.

Phase 1 must answer quickly, so this module only asks Elide for the requested
spectral group and flattens each ``Observation`` into a small, JSON-serializable
metadata dict.  Matrix payloads (FITS arrays, masks) never leave this layer, and
the preview URL is a presentation concern built by the router.
"""

from __future__ import annotations

from pathlib import Path

from spherex_pipeline import Observation, get_observations
from spherex_pipeline.constants import DEFAULT_QR

# Phase 1 queries the current searchable SPHEREx catalog (DR1; QR2 ya no se indexa).
_QR = DEFAULT_QR
_SOURCE = "irsa"


def _to_metadata(observation: Observation) -> dict:
    """Flatten one ``Observation`` into the Phase 1 metadata contract.

    ``Observation.to_summary()`` already strips the scientific matrices and
    keeps ``survey_index`` inside ``metadata``; this helper only renames ``id``
    to ``obs_id`` and lifts ``survey_index`` to the top level.
    """
    summary = observation.to_summary()
    metadata = summary.get("metadata") or {}
    return {
        "obs_id": summary["id"],
        "timestamp": summary["timestamp"],
        "detector": summary["detector"],
        "wavelength": summary["wavelength"],
        "bandwidth": summary["bandwidth"],
        "survey_index": metadata.get("survey_index"),
        "fits_source": summary["fits_source"],
        "shape": summary["shape"],
        "n_invalid_pixels": summary["n_invalid_pixels"],
    }


def fetch_phase1_metadata(
    ra: float,
    dec: float,
    size_deg: float,
    bandpass: str,
    spectral_group: int,
    cache_dir: str | Path,
) -> list[dict]:
    """Return the metadata of the frames in one spectral group.

    Args:
        ra: Right ascension of the cutout center, in degrees.
        dec: Declination of the cutout center, in degrees.
        size_deg: Cutout side size, in degrees (Elide's ``size`` argument).
        bandpass: SPHEREx band/detector identifier, e.g. ``"SPHEREx-D4"``.
        spectral_group: Spectral group to isolate, from 1 to 17.
        cache_dir: Directory where Elide caches downloaded cutouts.

    Returns:
        One dict per frame, ordered as Elide returns them, with the keys
        ``obs_id``, ``timestamp``, ``detector``, ``wavelength``, ``bandwidth``,
        ``survey_index``, ``fits_source``, ``shape`` and ``n_invalid_pixels``.
        An empty list means the requested group has no frames for the region.
    """
    observations = _load_group(ra, dec, size_deg, bandpass, spectral_group, cache_dir)
    return [_to_metadata(observation) for observation in observations]


def fetch_phase1_metadata_and_observations(
    ra: float,
    dec: float,
    size_deg: float,
    bandpass: str,
    spectral_group: int,
    cache_dir: str | Path,
) -> tuple[list[dict], list[Observation]]:
    """Return Phase 1 metadata plus the in-memory ``Observation`` objects.

    ``get_observations`` from Elide already downloads the cutouts and builds the
    ``Observation`` objects (with their ``.image`` NumPy matrices), so there is
    no need to download the same FITS twice.  The metadata dicts go to the HTTP
    202 response; the ``Observation`` objects are kept in memory for the PNG
    render, RGB composite and Etner motion phases.
    """
    observations = _load_group(ra, dec, size_deg, bandpass, spectral_group, cache_dir)
    return [_to_metadata(observation) for observation in observations], observations


def _load_group(
    ra: float,
    dec: float,
    size_deg: float,
    bandpass: str,
    spectral_group: int,
    cache_dir: str | Path,
) -> list[Observation]:
    return get_observations(
        ra,
        dec,
        size_deg,
        qr=_QR,
        bandpass=bandpass,
        group=spectral_group,
        source=_SOURCE,
        cache_dir=cache_dir,
    )
