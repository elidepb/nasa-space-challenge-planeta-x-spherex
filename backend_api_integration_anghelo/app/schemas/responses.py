"""Response DTOs with native Pydantic v2 validation."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ObservationSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: str
    detector: int
    wavelength: Optional[float] = None
    bandwidth: Optional[float] = None
    fits_source: str
    shape: Optional[List[int]] = None
    n_invalid_pixels: Optional[int] = None


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    estado: str
    progreso_porcentaje: float
    total_observaciones_grupo: int
    observaciones_descargadas: int
    candidatos_detectados: int
    error_detail: Optional[str] = None


class ImageListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    obs_id: str
    survey_index: int
    wavelength_um: float
    shape: List[int]
    preview_png_url: str
    fits_download_url: str


class ImageListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    total_imagenes: int
    imagenes: List[ImageListItemSchema]


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    estado: str
    message: str
    spectral_group: int
    observaciones: List[ObservationSummarySchema]


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    total_candidatos: int
    candidatos: List[dict]
