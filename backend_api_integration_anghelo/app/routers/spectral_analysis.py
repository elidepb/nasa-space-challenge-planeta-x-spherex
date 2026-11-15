"""Minimalist FastAPI router for SPHEREx rapid in-memory analysis without polling.

Exposes:
- GET /analyze: synchronous 1-2 second analysis returning original/residual Base64 PNGs and moving candidates.
- GET /sed: 102-channel SPHEREx spectral energy distribution with methane CH4 absorption band.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from fastapi import APIRouter, Query

from app.services.spherex_pipeline import (
    compute_spectral_sed,
    process_region_in_memory,
    query_crossmatch_catalogs,
)

router = APIRouter(tags=["SPHEREx Rapid Analysis"])


@lru_cache(maxsize=128)
def cached_analysis(ra: float, dec: float, size: float, band: str, source: str = "auto"):
    return process_region_in_memory(round(ra, 5), round(dec, 5), size, band, source=source)


@router.get("/analyze")
async def analyze_sky_region(
    ra: float = Query(..., ge=0.0, lt=360.0, description="Right ascension in degrees"),
    dec: float = Query(..., ge=-90.0, le=90.0, description="Declination in degrees"),
    size: float = Query(180.0, ge=1.0, le=14400.0, description="Cutout size in arcsec"),
    band: str = Query("D1", description="SPHEREx band/detector (D1 through D6)"),
    source: str = Query("auto", description="'auto', 'irsa', or 'demo'"),
):
    """Returns in a single synchronous call all aligned epochs (original + residual without stars) and candidates."""
    return await asyncio.to_thread(cached_analysis, ra, dec, size, band, source)


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
