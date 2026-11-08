"""Request DTOs with native Pydantic v2 validation."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, ConfigDict


class AnalysisCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ra: Annotated[float, Field(ge=0, le=360, description="Right ascension in degrees")]
    dec: Annotated[float, Field(ge=-90, le=90, description="Declination in degrees")]
    size_deg: Annotated[float, Field(gt=0, description="Cutout side size in degrees")]
    bandpass: str = Field(default="SPHEREx-D2", description="SPHEREx band/detector")
    spectral_group: Annotated[
        int, Field(ge=1, le=17, description="Spectral group 1-17")
    ] = 5


class RGBCompositeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    red_obs_id: str = Field(..., description="Observation id for the red channel")
    green_obs_id: str = Field(..., description="Observation id for the green channel")
    blue_obs_id: str = Field(..., description="Observation id for the blue channel")
