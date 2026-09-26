from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from storm_nowcast.models.schemas import _as_utc


SensorKind = Literal["RAINFALL", "SATELLITE", "RADAR", "LIGHTNING", "SURFACE", "NWP"]
VariableStatus = Literal["OBSERVED", "DERIVED", "FORECAST"]


class SourceDescriptor(BaseModel):
    provider: str
    product: str
    sensor: SensorKind
    official_url: str
    access_method: str
    authentication_required: bool = False

    @field_validator("official_url")
    @classmethod
    def require_official_https_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("official_url must use HTTPS")
        return value


class RawAsset(BaseModel):
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    source: SourceDescriptor
    acquired_at: datetime | None = None
    is_synthetic: bool = False

    @field_validator("acquired_at", mode="before")
    @classmethod
    def normalize_acquired_at(cls, value: datetime | str | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class SpatialResolution(BaseModel):
    grid_spacing_km: float | None = Field(default=None, gt=0)
    native_description: str | None = None
    effective_resolution_note: str | None = None
    crs: str = "EPSG:4326"

    @model_validator(mode="after")
    def require_resolution_description(self) -> "SpatialResolution":
        if self.grid_spacing_km is None and not self.native_description:
            raise ValueError("A numeric grid spacing or native description is required")
        return self


class TemporalSupport(BaseModel):
    observation_start: datetime
    observation_end: datetime
    native_resolution_minutes: float | None = Field(default=None, gt=0)
    availability_time: datetime | None = None

    _utc_times = field_validator(
        "observation_start", "observation_end", "availability_time", mode="before"
    )(lambda value: _as_utc(value) if value is not None else None)

    @model_validator(mode="after")
    def validate_window(self) -> "TemporalSupport":
        if self.observation_start > self.observation_end:
            raise ValueError("observation_start must not be after observation_end")
        return self


class VariableLineage(BaseModel):
    variable: str
    source_record_ids: list[str] = Field(min_length=1)
    status: VariableStatus
    native_units: str
    processed_units: str
    native_spatial_resolution: SpatialResolution
    analysis_grid_resolution_km: float | None = Field(default=None, gt=0)
    resampling_method: str = "none"
    native_temporal_resolution_minutes: float | None = Field(default=None, gt=0)
    processing_steps: list[str] = Field(default_factory=list)

    @property
    def is_resampled_to_finer_grid(self) -> bool:
        native = self.native_spatial_resolution.grid_spacing_km
        return bool(
            native is not None
            and self.analysis_grid_resolution_km is not None
            and self.analysis_grid_resolution_km < native
        )
