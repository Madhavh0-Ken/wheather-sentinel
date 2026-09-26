from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.detection.storms import detect_cells
from storm_nowcast.eta.calculator import calculate_eta
from storm_nowcast.hazards.extreme_rain import score_extreme_rain_risk
from storm_nowcast.models.schemas import ETAResult, StormCell
from storm_nowcast.nowcast.motion import forecast_track
from storm_nowcast.preprocessing.validation import validate_weather_dataset
from storm_nowcast.tracking.tracker import CellTracker


def _utc_datetime(value: np.datetime64) -> datetime:
    nanoseconds = value.astype("datetime64[ns]").astype(np.int64)
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)


@dataclass(frozen=True)
class ReplaySnapshot:
    frame_index: int
    timestamp: datetime
    rainfall: xr.DataArray
    tracks: list[StormCell]
    eta_by_track: dict[str, ETAResult]
    observation_times: tuple[datetime, ...]


def score_event(dataset: xr.Dataset, threshold_mm_hr: float) -> float:
    values = np.asarray(dataset.rain_rate.values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    wet_frames = int(np.sum(np.nanmax(values, axis=(1, 2)) >= threshold_mm_hr))
    return float(np.nanpercentile(finite, 99) + wet_frames * 10)


def save_event(dataset: xr.Dataset, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = dataset.copy(deep=False)
    serializable.attrs = dict(dataset.attrs)
    if isinstance(serializable.attrs.get("is_synthetic"), (bool, np.bool_)):
        serializable.attrs["is_synthetic"] = int(serializable.attrs["is_synthetic"])
    encoding = {
        name: {"compression": "gzip", "compression_opts": 4, "shuffle": True}
        for name in serializable.data_vars
    }
    serializable.to_netcdf(path, engine="h5netcdf", encoding=encoding)


class ReplayPlayer:
    def __init__(self, dataset: xr.Dataset, settings: Settings) -> None:
        self.dataset = validate_weather_dataset(dataset)
        self.settings = settings

    @property
    def frame_count(self) -> int:
        return self.dataset.sizes["time"]

    def _tracks_through(self, frame_index: int) -> tuple[list[StormCell], tuple[datetime, ...]]:
        tracker = CellTracker(self.settings.tracking)
        observation_times: list[datetime] = []
        current: list[StormCell] = []
        for index in range(frame_index + 1):
            timestamp = _utc_datetime(self.dataset.time.values[index])
            observation_times.append(timestamp)
            field = self.dataset.rain_rate.isel(time=index).copy(deep=False)
            field.attrs["is_synthetic"] = bool(self.dataset.attrs.get("is_synthetic", False))
            detections = detect_cells(field, timestamp, self.settings.detection)
            current = tracker.update(detections, timestamp)
        return current, tuple(observation_times)

    def analyze(self, frame_index: int, target: tuple[float, float]) -> ReplaySnapshot:
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"frame index must be between 0 and {self.frame_count - 1}")
        tracks, observation_times = self._tracks_through(frame_index)
        enriched: list[StormCell] = []
        eta_by_track: dict[str, ETAResult] = {}
        for track in tracks:
            forecasts = (
                forecast_track(
                    track,
                    self.settings.forecast.lead_minutes,
                    base_uncertainty_km=self.settings.forecast.base_uncertainty_km,
                    uncertainty_growth_km_per_hour=self.settings.forecast.uncertainty_growth_km_per_hour,
                )
                if len(track.history) >= 2
                else []
            )
            risk = score_extreme_rain_risk(track)
            updated = track.model_copy(update={"forecasts": forecasts, "risk": risk})
            enriched.append(updated)
            eta_by_track[track.id] = calculate_eta(target[0], target[1], forecasts, track.last_seen)
        timestamp = observation_times[-1]
        return ReplaySnapshot(
            frame_index=frame_index,
            timestamp=timestamp,
            rainfall=self.dataset.rain_rate.isel(time=frame_index),
            tracks=enriched,
            eta_by_track=eta_by_track,
            observation_times=observation_times,
        )

    def all_tracks(self) -> list[StormCell]:
        tracker = CellTracker(self.settings.tracking)
        for index in range(self.frame_count):
            timestamp = _utc_datetime(self.dataset.time.values[index])
            field = self.dataset.rain_rate.isel(time=index).copy(deep=False)
            field.attrs["is_synthetic"] = bool(self.dataset.attrs.get("is_synthetic", False))
            tracker.update(detect_cells(field, timestamp, self.settings.detection), timestamp)
        return list(tracker.tracks.values())
