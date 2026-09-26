from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import xarray as xr

from storm_nowcast.models.schemas import ForecastPoint


@dataclass(frozen=True)
class MotionEstimate:
    available: bool
    shift_y_pixels: float = 0.0
    shift_x_pixels: float = 0.0
    finite_coverage: float = 0.0
    quality: float | None = None
    explanation: str = ""


@dataclass(frozen=True)
class ForecastField:
    lead_minutes: int
    valid_at: datetime
    rain_rate: xr.DataArray
    uncertainty_km: float
    confidence: str


@dataclass(frozen=True)
class RasterForecastProduct:
    issued_at: datetime
    method: str
    motion: MotionEstimate
    fields: list[ForecastField] = field(default_factory=list)
    point_forecasts: list[ForecastPoint] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None


class RasterNowcaster(Protocol):
    name: str

    def forecast(self, previous: xr.DataArray, current: xr.DataArray, *, issued_at: datetime) -> RasterForecastProduct: ...
