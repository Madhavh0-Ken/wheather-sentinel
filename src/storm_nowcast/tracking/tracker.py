from __future__ import annotations

from datetime import datetime

import numpy as np
from pyproj import Geod
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

from storm_nowcast.config import TrackingConfig
from storm_nowcast.models.schemas import CellObservation, DetectedCell, StormCell


WGS84 = Geod(ellps="WGS84")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    _, _, distance_m = WGS84.inv(lon1, lat1, lon2, lat2)
    return abs(distance_m) / 1000


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    forward, _, _ = WGS84.inv(lon1, lat1, lon2, lat2)
    return forward % 360


def _iou(first: dict, second: dict) -> float:
    first_shape = shape(first)
    second_shape = shape(second)
    union = first_shape.union(second_shape).area
    return float(first_shape.intersection(second_shape).area / union) if union else 0.0


def _observation(detection: DetectedCell) -> CellObservation:
    return CellObservation(
        timestamp=detection.timestamp,
        centroid_lat=detection.centroid_lat,
        centroid_lon=detection.centroid_lon,
        area_km2=detection.area_km2,
        max_intensity=detection.max_intensity,
        mean_intensity=detection.mean_intensity,
        bbox=detection.bbox,
        polygon_geojson=detection.polygon_geojson,
    )


class CellTracker:
    def __init__(self, config: TrackingConfig | None = None) -> None:
        self.config = config or TrackingConfig()
        self.tracks: dict[str, StormCell] = {}
        self._next_id = 1

    def _new_track(self, detection: DetectedCell) -> StormCell:
        track_id = f"IPC-{self._next_id:03d}"
        self._next_id += 1
        observation = _observation(detection)
        track = StormCell(
            id=track_id,
            history=[observation],
            first_seen=detection.timestamp,
            last_seen=detection.timestamp,
            is_synthetic=detection.is_synthetic,
        )
        self.tracks[track_id] = track
        return track

    def _cost(self, track: StormCell, detection: DetectedCell) -> float:
        current = track.current
        distance = haversine_km(
            current.centroid_lat,
            current.centroid_lon,
            detection.centroid_lat,
            detection.centroid_lon,
        )
        if distance > self.config.max_distance_km:
            return 1_000_000.0
        overlap_penalty = 1.0 - _iou(current.polygon_geojson, detection.polygon_geojson)
        intensity_scale = max(current.max_intensity, detection.max_intensity, 1.0)
        intensity_penalty = abs(current.max_intensity - detection.max_intensity) / intensity_scale
        return distance / self.config.max_distance_km + 0.35 * overlap_penalty + 0.15 * intensity_penalty

    def _append(self, track: StormCell, detection: DetectedCell) -> StormCell:
        previous = track.current
        current = _observation(detection)
        elapsed_hours = (current.timestamp - previous.timestamp).total_seconds() / 3600
        if elapsed_hours <= 0:
            raise ValueError("Tracking observations must advance in time")
        distance = haversine_km(
            previous.centroid_lat,
            previous.centroid_lon,
            current.centroid_lat,
            current.centroid_lon,
        )
        bearing = (
            initial_bearing_deg(
                previous.centroid_lat,
                previous.centroid_lon,
                current.centroid_lat,
                current.centroid_lon,
            )
            if distance > 0.01
            else track.bearing_deg
        )
        updated = StormCell(
            id=track.id,
            history=[*track.history, current],
            speed_kmh=distance / elapsed_hours,
            bearing_deg=bearing,
            intensity_trend_mm_hr_per_hour=(current.max_intensity - previous.max_intensity) / elapsed_hours,
            growth_trend_km2_per_hour=(current.area_km2 - previous.area_km2) / elapsed_hours,
            first_seen=track.first_seen,
            last_seen=current.timestamp,
            forecasts=track.forecasts,
            risk=track.risk,
            active=True,
            is_synthetic=track.is_synthetic or detection.is_synthetic,
        )
        self.tracks[track.id] = updated
        return updated

    def update(self, detections: list[DetectedCell], timestamp: datetime) -> list[StormCell]:
        for track_id, track in list(self.tracks.items()):
            self.tracks[track_id] = track.model_copy(update={"active": False})

        candidates = [
            track
            for track in self.tracks.values()
            if 0 < (timestamp - track.last_seen).total_seconds() / 60 <= self.config.max_gap_minutes
        ]
        matched_detections: set[int] = set()
        observed: list[StormCell] = []
        if candidates and detections:
            costs = np.array([[self._cost(track, detection) for detection in detections] for track in candidates])
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows, columns, strict=True):
                if costs[row, column] <= self.config.max_assignment_cost:
                    observed.append(self._append(candidates[row], detections[column]))
                    matched_detections.add(column)

        for index, detection in enumerate(detections):
            if index not in matched_detections:
                observed.append(self._new_track(detection))
        return sorted(observed, key=lambda item: item.id)
