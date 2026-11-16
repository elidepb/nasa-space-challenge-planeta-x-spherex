"""Minimalist FastAPI router for SPHEREx rapid in-memory analysis without polling.

Exposes:
- GET /analyze: synchronous 1-2 second analysis returning original/residual Base64 PNGs and moving candidates.
- GET /sed: 102-channel SPHEREx spectral energy distribution with methane CH4 absorption band.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.services.spherex_pipeline import (
    compute_spectral_sed,
    make_synthetic_observations,
    process_region_in_memory,
    query_crossmatch_catalogs,
    render_sky_png,
)

router = APIRouter(tags=["SPHEREx Rapid Analysis"])


@lru_cache(maxsize=128)
def cached_analysis(
    ra: float,
    dec: float,
    size: float,
    band: str,
    band_index: int | None = None,
    wavelength_um: float | None = None,
    source: str = "auto",
):
    return process_region_in_memory(
        round(ra, 5),
        round(dec, 5),
        size,
        band,
        band_index=band_index,
        wavelength_um=wavelength_um,
        source=source,
    )


@router.get("/analyze")
async def analyze_sky_region(
    ra: float = Query(..., ge=0.0, lt=360.0, description="Right ascension in degrees"),
    dec: float = Query(..., ge=-90.0, le=90.0, description="Declination in degrees"),
    size: float = Query(180.0, ge=1.0, le=14400.0, description="Cutout size in arcsec"),
    band: str = Query("D1", description="SPHEREx band/detector (D1 through D6)"),
    band_index: int | None = Query(default=None, ge=1, le=102, description="Global band index 1..102"),
    wavelength_um: float | None = Query(default=None, description="Exact wavelength in microns"),
    source: str = Query("auto", description="'auto', 'irsa', or 'demo'"),
):
    """Returns in a single synchronous call all aligned epochs (original + residual without stars) and candidates."""
    return await asyncio.to_thread(
        cached_analysis,
        ra,
        dec,
        size,
        band,
        band_index,
        wavelength_um,
        source,
    )


@router.get("/sky-image")
def get_sky_image(
    ra: float = Query(...),
    dec: float = Query(...),
    band_index: int | None = Query(default=None, ge=1, le=102),
    wavelength_um: float | None = Query(default=None),
    band: str | None = Query(default=None),
):
    obs = make_synthetic_observations(
        ra=ra,
        dec=dec,
        band_index=band_index,
        wavelength_um=wavelength_um,
        detector=band,
    )
    png_bytes = render_sky_png(obs)
    resolved = obs["band"]

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Band-Index": str(resolved.band_index),
            "X-Wavelength-Um": str(resolved.wavelength_um),
            "X-Detector": resolved.detector,
        },
    )


@router.get("/sed")
async def get_candidate_sed(
    ra: float = Query(..., ge=0.0, lt=360.0, description="Right ascension in degrees"),
    dec: float = Query(..., ge=-90.0, le=90.0, description="Declination in degrees"),
):
    """Returns the 102-channel SPHEREx SED (0.75 µm to 5.0 µm) with CH4 absorption at 3.3 µm."""
    return await asyncio.to_thread(compute_spectral_sed, round(ra, 5), round(dec, 5))


@router.get("/crossmatch")
async def crossmatch_catalogs(
    ra: float = Query(..., ge=0.0, lt=360.0, description="Right ascension in degrees"),
    dec: float = Query(..., ge=-90.0, le=90.0, description="Declination in degrees"),
    radius: float = Query(180.0, ge=1.0, le=3600.0, description="Search radius in arcsec"),
    mjd: float = Query(60400.0, description="Epoch MJD"),
):
    """Crossmatches live Gaia DR3 and SkyBoT catalogs without browser CORS restrictions."""
    return await asyncio.to_thread(query_crossmatch_catalogs, round(ra, 5), round(dec, 5), mjd, radius)
