from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class ProvenanceRecord(BaseModel):
    provider: str
    product: str
    source_url: str
    acquired_at: datetime
    observation_start: datetime
    observation_end: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    processing_steps: list[str] = Field(default_factory=list)
    local_file: str | None = None
    is_synthetic: bool = False

    _utc_times = field_validator(
        "acquired_at", "observation_start", "observation_end", mode="before"
    )(_as_utc)


class DetectedCell(BaseModel):
    local_id: int
    timestamp: datetime
    centroid_lat: float = Field(ge=-90, le=90)
    centroid_lon: float = Field(ge=-180, le=360)
    area_km2: float = Field(gt=0)
    max_intensity: float = Field(ge=0)
    mean_intensity: float = Field(ge=0)
    pixel_count: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    polygon_geojson: dict[str, Any]
    is_synthetic: bool = False

    _utc_timestamp = field_validator("timestamp", mode="before")(_as_utc)


class CellObservation(BaseModel):
    timestamp: datetime
    centroid_lat: float
    centroid_lon: float
    area_km2: float = Field(gt=0)
    max_intensity: float = Field(ge=0)
    mean_intensity: float = Field(ge=0)
    bbox: tuple[float, float, float, float]
    polygon_geojson: dict[str, Any]

    _utc_timestamp = field_validator("timestamp", mode="before")(_as_utc)


class ForecastPoint(BaseModel):
    lead_minutes: int = Field(gt=0)
    valid_at: datetime
    latitude: float
    longitude: float
    uncertainty_km: float = Field(gt=0)
    confidence: Literal["LOW", "MEDIUM", "HIGH"]

    _utc_valid = field_validator("valid_at", mode="before")(_as_utc)


class RiskAssessment(BaseModel):
    score: float = Field(ge=0, le=100)
    level: Literal["LOW", "MODERATE", "HIGH", "VERY HIGH"]
    contributors: list[str]
    factors: dict[str, float]


class StormCell(BaseModel):
    id: str
    history: list[CellObservation]
    speed_kmh: float = Field(default=0, ge=0)
    bearing_deg: float | None = Field(default=None, ge=0, lt=360)
    intensity_trend_mm_hr_per_hour: float = 0
    growth_trend_km2_per_hour: float = 0
    first_seen: datetime
    last_seen: datetime
    forecasts: list[ForecastPoint] = Field(default_factory=list)
    risk: RiskAssessment | None = None
    active: bool = True
    is_synthetic: bool = False

    _utc_times = field_validator("first_seen", "last_seen", mode="before")(_as_utc)

    @model_validator(mode="after")
    def validate_history(self) -> "StormCell":
        if not self.history:
            raise ValueError("StormCell history cannot be empty")
        if self.first_seen > self.last_seen:
            raise ValueError("first_seen must not be after last_seen")
        return self

    @property
    def current(self) -> CellObservation:
        return self.history[-1]


class ETAResult(BaseModel):
    approaches_target: bool
    closest_distance_km: float = Field(ge=0)
    closest_lead_minutes: int | None = None
    uncertainty_km: float | None = None
    estimated_arrival: datetime | None = None
    explanation: str

    @field_validator("estimated_arrival", mode="before")
    @classmethod
    def validate_eta(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class EvaluationMetrics(BaseModel):
    lead_minutes: int | None = None
    position_error_km: float | None = Field(default=None, ge=0)
    iou: float | None = Field(default=None, ge=0, le=1)
    track_continuity: float | None = Field(default=None, ge=0, le=1)
    sample_count: int = Field(default=0, ge=0)
    message: str | None = None
