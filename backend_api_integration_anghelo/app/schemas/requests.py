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


class ChannelRequest(BaseModel):
    """Definition of one RGB channel: which SPHEREx detector and spectral group to fetch."""

    model_config = ConfigDict(from_attributes=True)

    channel: str = Field(
        ...,
        pattern="^(red|green|blue)$",
        description="Color channel (red, green or blue)",
    )
    sensor: Annotated[
        int, Field(ge=1, le=6, description="SPHEREx detector number 1-6")
    ] = Field(..., description="SPHEREx detector number 1-6")
    group: Annotated[
        int, Field(ge=1, le=17, description="Spectral group 1-17")
    ] = Field(..., description="Spectral group 1-17")


class RGBCompositeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ra: Annotated[float, Field(ge=0, le=360, description="Right ascension in degrees")]
    dec: Annotated[float, Field(ge=-90, le=90, description="Declination in degrees")]
    size_deg: Annotated[
        float, Field(gt=0, description="Cutout side size in degrees")
    ] = 0.85
    channels: Annotated[
        list[ChannelRequest],
        Field(
            ...,
            min_length=1,
            max_length=3,
            description="Channel definitions (one per RGB channel)",
        ),
    ]
