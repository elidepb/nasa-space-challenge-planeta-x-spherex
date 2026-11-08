"""FastAPI application entry point: lifespan, CORS, global exception handlers and routers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import ensure_data_volumes
from app.core.config import settings
from app.routers import spectral_analysis


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001 - app kept for FastAPI signature
    ensure_data_volumes()
    yield


app = FastAPI(
    title="Backend API Integration — SPHEREx Planet X",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spectral_analysis.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "storage_type": settings.STORAGE_TYPE}


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):  # noqa: ARG001
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"detail": str(exc)})
