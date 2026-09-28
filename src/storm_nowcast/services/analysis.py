from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import xarray as xr
from pydantic import BaseModel, Field

from storm_nowcast.confidence.framework import ConfidenceEstimate, estimate_forecast_confidence
from storm_nowcast.config import Settings
from storm_nowcast.hazards.registry import HazardAssessment, assess_hazards
from storm_nowcast.models.schemas import ETAResult, ForecastPoint
from storm_nowcast.models.twin import SatelliteVariableSummary
from storm_nowcast.replay.player import ReplayPlayer
from storm_nowcast.tracking.twin import build_multisensor_twin


class TrackSnapshot(BaseModel):
    id: str
    latitude: float
    longitude: float
    age_minutes: int
    speed_kmh: float
    bearing_deg: float | None
    maximum_rain_rate: float
    area_km2: float
    intensity_trend_mm_hr_per_hour: float
    growth_trend_km2_per_hour: float
    sensor_availability: dict[str, str]
    forecasts: list[ForecastPoint]
    confidence: ConfidenceEstimate
    hazards: list[HazardAssessment]
    eta: ETAResult


class AnalysisSnapshot(BaseModel):
    event_id: str
    mode: Literal["HISTORICAL_REPLAY", "LIVE"]
    frame_index: int
    frame_count: int
    observation_time: datetime
    issue_time: datetime
    source_times: list[datetime]
    target: tuple[float, float]
    tracks: list[TrackSnapshot]
    is_synthetic: bool
    insat_available: bool = False
    insat_observation_time: datetime | None = None
    insat_age_minutes: float | None = None
    insat_product: str | None = None
    insat_provider: str | None = None
    insat_source_file: str | None = None
    insat_provenance: dict[str, Any] | None = None
    insat_variables: list[SatelliteVariableSummary] = Field(default_factory=list)


class AnalysisService:
    def __init__(self, player: ReplayPlayer, *, event_id: str) -> None:
        self.player = player
        self.event_id = event_id

    @classmethod
    def from_dataset(
        cls,
        dataset: xr.Dataset,
        *,
        settings: Settings,
        event_id: str,
        satellite_cube: xr.Dataset | None = None,
    ) -> "AnalysisService":
        return cls(
            ReplayPlayer(dataset, settings, satellite_cube=satellite_cube),
            event_id=event_id,
        )

    def snapshot(self, *, frame_index: int, target: tuple[float, float]) -> AnalysisSnapshot:
        replay = self.player.analyze(frame_index, target)
        tracks: list[TrackSnapshot] = []
        for track in replay.tracks:
            twin = build_multisensor_twin(
                track,
                replay.sensor_evidence_by_track.get(track.id, []),
            )
            confidence = estimate_forecast_confidence(twin, lead_minutes=30)
            tracks.append(
                TrackSnapshot(
                    id=track.id,
                    latitude=track.current.centroid_lat,
                    longitude=track.current.centroid_lon,
                    age_minutes=twin.age_minutes,
                    speed_kmh=track.speed_kmh,
                    bearing_deg=track.bearing_deg,
                    maximum_rain_rate=track.current.max_intensity,
                    area_km2=track.current.area_km2,
                    intensity_trend_mm_hr_per_hour=track.intensity_trend_mm_hr_per_hour,
                    growth_trend_km2_per_hour=track.growth_trend_km2_per_hour,
                    sensor_availability={str(key): value for key, value in twin.sensor_availability.items()},
                    forecasts=track.forecasts,
                    confidence=confidence,
                    hazards=assess_hazards(track),
                    eta=replay.eta_by_track[track.id],
                )
            )
        return AnalysisSnapshot(
            event_id=self.event_id,
            mode="HISTORICAL_REPLAY",
            frame_index=frame_index,
            frame_count=self.player.frame_count,
            observation_time=replay.timestamp,
            issue_time=replay.timestamp,
            source_times=list(replay.observation_times),
            target=target,
            tracks=tracks,
            is_synthetic=bool(self.player.dataset.attrs.get("is_synthetic", False)),
            insat_available=replay.insat.available,
            insat_observation_time=replay.insat.observation_time,
            insat_age_minutes=replay.insat.age_minutes,
            insat_product=replay.insat.product,
            insat_provider=replay.insat.provider,
            insat_source_file=replay.insat.source_file,
            insat_provenance=replay.insat.provenance,
            insat_variables=list(replay.insat.variables),
        )
