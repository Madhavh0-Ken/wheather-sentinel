from datetime import datetime, timedelta, timezone

import pytest

from storm_nowcast.config import TrackingConfig
from storm_nowcast.models.schemas import DetectedCell
from storm_nowcast.tracking.tracker import CellTracker, haversine_km, initial_bearing_deg


BASE = datetime(2023, 7, 9, 0, tzinfo=timezone.utc)


def cell(local_id, timestamp, lat, lon, intensity=20.0, area=100.0):
    half = 0.05
    return DetectedCell(
        local_id=local_id,
        timestamp=timestamp,
        centroid_lat=lat,
        centroid_lon=lon,
        area_km2=area,
        max_intensity=intensity,
        mean_intensity=intensity - 2,
        pixel_count=4,
        bbox=(lat - half, lon - half, lat + half, lon + half),
        polygon_geojson={
            "type": "Polygon",
            "coordinates": [[
                [lon - half, lat - half], [lon + half, lat - half],
                [lon + half, lat + half], [lon - half, lat + half],
                [lon - half, lat - half],
            ]],
        },
        is_synthetic=True,
    )


def test_geodesic_distance_and_bearing_are_physically_sensible():
    assert haversine_km(30, 75, 31, 75) == pytest.approx(110.86, rel=0.01)
    assert initial_bearing_deg(30, 75, 31, 75) == pytest.approx(0, abs=0.5)
    assert initial_bearing_deg(30, 75, 30, 76) == pytest.approx(89.75, abs=1)


def test_tracker_keeps_id_and_uses_actual_missing_frame_time_delta():
    tracker = CellTracker(TrackingConfig(max_distance_km=100, max_gap_minutes=90))
    first = tracker.update([cell(1, BASE, 30, 75, intensity=20, area=100)], BASE)
    later_time = BASE + timedelta(minutes=60)
    later = tracker.update([cell(1, later_time, 30.45, 75, intensity=30, area=130)], later_time)

    assert first[0].id == "IPC-001"
    assert later[0].id == "IPC-001"
    assert len(later[0].history) == 2
    assert later[0].speed_kmh == pytest.approx(49.9, rel=0.03)
    assert later[0].bearing_deg == pytest.approx(0, abs=0.5)
    assert later[0].intensity_trend_mm_hr_per_hour == pytest.approx(10)
    assert later[0].growth_trend_km2_per_hour == pytest.approx(30)


def test_tracker_assigns_new_id_to_distant_cell_and_marks_disappearance():
    tracker = CellTracker(TrackingConfig(max_distance_km=40, max_gap_minutes=90))
    tracker.update([cell(1, BASE, 30, 75)], BASE)
    next_time = BASE + timedelta(minutes=30)
    current = tracker.update([cell(1, next_time, 32, 78)], next_time)

    assert current[0].id == "IPC-002"
    assert tracker.tracks["IPC-001"].active is False
    assert tracker.tracks["IPC-002"].active is True


def test_overlap_can_disambiguate_two_nearby_cells():
    tracker = CellTracker(TrackingConfig(max_distance_km=100, max_gap_minutes=90))
    tracker.update(
        [cell(1, BASE, 30.0, 75.0), cell(2, BASE, 30.0, 75.3)],
        BASE,
    )
    next_time = BASE + timedelta(minutes=30)
    result = tracker.update(
        [cell(1, next_time, 30.0, 75.28), cell(2, next_time, 30.0, 75.02)],
        next_time,
    )

    by_id = {track.id: track.current.centroid_lon for track in result}
    assert by_id["IPC-001"] == pytest.approx(75.02)
    assert by_id["IPC-002"] == pytest.approx(75.28)
