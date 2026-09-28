from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.detection.storms import detect_cells
from storm_nowcast.eta.calculator import calculate_eta
from storm_nowcast.hazards.extreme_rain import score_extreme_rain_risk
from storm_nowcast.models.schemas import ETAResult, StormCell
from storm_nowcast.models.twin import SatelliteVariableSummary, SensorEvidence
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
    insat: SatelliteFrameEvidence
    sensor_evidence_by_track: dict[str, list[SensorEvidence]]


@dataclass(frozen=True)
class SatelliteFrameEvidence:
    available: bool
    observation_time: datetime | None = None
    age_minutes: float | None = None
    provider: str | None = None
    product: str | None = None
    source_file: str | None = None
    source_record_id: str | None = None
    provenance: dict[str, Any] | None = None
    variables: tuple[SatelliteVariableSummary, ...] = ()
    data: xr.Dataset | None = None


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
    def __init__(
        self,
        dataset: xr.Dataset,
        settings: Settings,
        *,
        satellite_cube: xr.Dataset | None = None,
    ) -> None:
        self.dataset = validate_weather_dataset(dataset)
        self.settings = settings
        if satellite_cube is not None:
            satellite_times = satellite_cube.time.values.astype("datetime64[ns]")
            replay_times = self.dataset.time.values.astype("datetime64[ns]")
            if not np.array_equal(satellite_times, replay_times):
                raise ValueError("Satellite cube times must exactly match replay times")
        self.satellite_cube = satellite_cube

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

    def _satellite_frame(self, frame_index: int) -> SatelliteFrameEvidence:
        if self.satellite_cube is None:
            return SatelliteFrameEvidence(available=False)
        cube = self.satellite_cube
        primary = "infrared_brightness_temperature"
        required = {
            primary,
            f"{primary}__missing",
            f"{primary}__observation_time",
            f"{primary}__age_minutes",
            f"{primary}__available",
            f"{primary}__source_file",
            f"{primary}__source_record_id",
            f"{primary}__provenance",
        }
        missing = required - set(cube.data_vars)
        if missing:
            raise ValueError(f"Satellite cube is missing fields: {sorted(missing)}")

        variable_names = [
            name
            for name, variable in cube.data_vars.items()
            if "__" not in name and variable.dims == ("time", "y", "x")
        ]
        frame_data_names = [
            name
            for variable in variable_names
            for name in (variable, f"{variable}__missing")
            if name in cube.data_vars
        ]
        data = cube[frame_data_names].isel(time=frame_index, drop=True)
        summaries: list[SatelliteVariableSummary] = []
        for variable in variable_names:
            values = np.asarray(data[variable].values, dtype=float)
            finite = np.isfinite(values)
            aligned = bool(cube[f"{variable}__available"].isel(time=frame_index).item())
            summaries.append(
                SatelliteVariableSummary(
                    name=variable,
                    source_variable=str(cube[variable].attrs.get("source_variable", "")),
                    units=str(cube[variable].attrs.get("units", "")),
                    calibration_lookup_table=cube[variable].attrs.get(
                        "calibration_lookup_table"
                    ),
                    native_spatial_resolution_km=cube[variable].attrs.get(
                        "native_spatial_resolution_km"
                    ),
                    available=aligned and bool(finite.any()),
                    missing_pixel_count=int((~finite).sum()),
                    total_pixel_count=int(values.size),
                )
            )

        selected_time = cube[f"{primary}__observation_time"].values[frame_index].astype(
            "datetime64[ns]"
        )
        observation_time = None if np.isnat(selected_time) else _utc_datetime(selected_time)
        age = float(cube[f"{primary}__age_minutes"].values[frame_index])
        age_minutes = age if np.isfinite(age) else None
        source_file = str(cube[f"{primary}__source_file"].values[frame_index]) or None
        source_record_id = str(
            cube[f"{primary}__source_record_id"].values[frame_index]
        ) or None
        raw_provenance = str(cube[f"{primary}__provenance"].values[frame_index])
        provenance = json.loads(raw_provenance) if raw_provenance else None
        primary_summary = next(item for item in summaries if item.name == primary)
        return SatelliteFrameEvidence(
            available=primary_summary.available,
            observation_time=observation_time,
            age_minutes=age_minutes,
            provider=str(cube.attrs.get("provider")) if cube.attrs.get("provider") else None,
            product=str(cube.attrs.get("product")) if cube.attrs.get("product") else None,
            source_file=source_file,
            source_record_id=source_record_id,
            provenance=provenance,
            variables=tuple(summaries),
            data=data,
        )

    @staticmethod
    def _satellite_evidence(
        track: StormCell,
        frame: SatelliteFrameEvidence,
    ) -> list[SensorEvidence]:
        if (
            not frame.available
            or frame.data is None
            or frame.observation_time is None
            or frame.source_record_id is None
        ):
            return []
        latitudes = np.asarray(frame.data.latitude.values, dtype=float)
        longitudes = np.asarray(frame.data.longitude.values, dtype=float)
        row = int(np.abs(latitudes - track.current.centroid_lat).argmin())
        column = int(np.abs(longitudes - track.current.centroid_lon).argmin())
        variables: dict[str, float] = {}
        for summary in frame.variables:
            if not summary.available:
                continue
            value = float(frame.data[summary.name].isel(y=row, x=column).item())
            if np.isfinite(value):
                variables[summary.name] = value
        if not variables:
            return []
        return [
            SensorEvidence(
                timestamp=frame.observation_time,
                sensor="SATELLITE",
                variables=variables,
                source_record_ids=[frame.source_record_id],
                quality_notes=[f"causal INSAT age {frame.age_minutes:g} minutes"],
            )
        ]

    def analyze(self, frame_index: int, target: tuple[float, float]) -> ReplaySnapshot:
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"frame index must be between 0 and {self.frame_count - 1}")
        tracks, observation_times = self._tracks_through(frame_index)
        insat = self._satellite_frame(frame_index)
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
        sensor_evidence_by_track = {
            track.id: self._satellite_evidence(track, insat) for track in enriched
        }
        return ReplaySnapshot(
            frame_index=frame_index,
            timestamp=timestamp,
            rainfall=self.dataset.rain_rate.isel(time=frame_index),
            tracks=enriched,
            eta_by_track=eta_by_track,
            observation_times=observation_times,
            insat=insat,
            sensor_evidence_by_track=sensor_evidence_by_track,
        )

    def all_tracks(self) -> list[StormCell]:
        tracker = CellTracker(self.settings.tracking)
        for index in range(self.frame_count):
            timestamp = _utc_datetime(self.dataset.time.values[index])
            field = self.dataset.rain_rate.isel(time=index).copy(deep=False)
            field.attrs["is_synthetic"] = bool(self.dataset.attrs.get("is_synthetic", False))
            tracker.update(detect_cells(field, timestamp, self.settings.detection), timestamp)
        return list(tracker.tracks.values())
