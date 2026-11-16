"""FastAPI application entry point: lifespan, CORS, global exception handlers and routers."""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure sibling packages (Elide and Etner) are on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("spherex_data_pipeline_elide", "scientific_motion_engine_etner"):
    _pkg_path = str(_PROJECT_ROOT / _pkg)
    if _pkg_path not in sys.path:
        sys.path.insert(0, _pkg_path)

from app.routers import spectral_analysis, analysis

app = FastAPI(
    title="SPHEREx Planet X - Rapid Engine API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spectral_analysis.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")

@app.get("/api/sky-image", tags=["SPHEREx Rapid Analysis"])
def sky_image_alias(
    ra: float,
    dec: float,
    band_index: int | None = None,
    wavelength_um: float | None = None,
    band: str | None = None,
):
    return spectral_analysis.get_sky_image(
        ra=ra,
        dec=dec,
        band_index=band_index,
        wavelength_um=wavelength_um,
        band=band,
    )


@app.get("/", tags=["root"])
async def root():
    return {
        "status": "online",
        "service": "SPHEREx Planet X - Rapid Engine API",
        "version": "2.0.0",
        "docs_url": "/docs",
        "health_url": "/health"
    }



@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "mode": "in-memory-temporal-median"}


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):  # noqa: ARG001
    return JSONResponse(status_code=400, content={"detail": str(exc)})
