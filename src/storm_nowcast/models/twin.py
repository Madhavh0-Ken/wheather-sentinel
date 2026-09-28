from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from storm_nowcast.models.schemas import StormCell, _as_utc
from storm_nowcast.models.sensors import SensorKind


AvailabilityState = Literal["AVAILABLE", "STALE", "UNAVAILABLE"]


class SensorEvidence(BaseModel):
    timestamp: datetime
    sensor: SensorKind
    variables: dict[str, float]
    source_record_ids: list[str] = Field(min_length=1)
    variable_status: Literal["OBSERVED", "DERIVED"] = "OBSERVED"
    quality_notes: list[str] = Field(default_factory=list)

    _utc_timestamp = field_validator("timestamp", mode="before")(_as_utc)


class SatelliteVariableSummary(BaseModel):
    name: str
    source_variable: str
    units: str
    calibration_lookup_table: str | None = None
    native_spatial_resolution_km: float | None = Field(default=None, gt=0)
    available: bool
    missing_pixel_count: int = Field(ge=0)
    total_pixel_count: int = Field(gt=0)


class MultiSensorStormCell(BaseModel):
    baseline: StormCell
    evidence_history: list[SensorEvidence] = Field(default_factory=list)
    sensor_availability: dict[SensorKind, AvailabilityState]
    current_features: dict[str, float] = Field(default_factory=dict)
    acceleration_kmh_per_hour: float | None = None

    @property
    def id(self) -> str:
        return self.baseline.id

    @property
    def age_minutes(self) -> int:
        return int((self.baseline.last_seen - self.baseline.first_seen).total_seconds() / 60)
