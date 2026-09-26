from datetime import datetime, timedelta, timezone

import pytest

from storm_nowcast.models.schemas import CellObservation, StormCell
from storm_nowcast.models.twin import SensorEvidence
from storm_nowcast.tracking.twin import build_multisensor_twin


def _observation(at, lon):
    return CellObservation(
        timestamp=at,
        centroid_lat=30.0,
        centroid_lon=lon,
        area_km2=100,
        max_intensity=20,
        mean_intensity=15,
        bbox=(29.9, lon - 0.1, 30.1, lon + 0.1),
        polygon_geojson={
            "type": "Polygon",
            "coordinates": [[[lon - 0.1, 29.9], [lon + 0.1, 29.9], [lon + 0.1, 30.1], [lon - 0.1, 30.1], [lon - 0.1, 29.9]]],
        },
    )


def _cell():
    start = datetime(2023, 7, 9, tzinfo=timezone.utc)
    history = [_observation(start, 75.0), _observation(start + timedelta(minutes=30), 75.05), _observation(start + timedelta(minutes=60), 75.15)]
    return StormCell(id="IPC-001", history=history, first_seen=start, last_seen=history[-1].timestamp, speed_kmh=20, bearing_deg=90)


def test_twin_tracks_sensor_availability_without_imputing_missing_sensors():
    cell = _cell()
    evidence = SensorEvidence(
        timestamp=cell.last_seen,
        sensor="SATELLITE",
        variables={"infrared_brightness_temperature": 235.0},
        source_record_ids=["sha256:abc"],
    )

    twin = build_multisensor_twin(cell, [evidence])

    assert twin.sensor_availability["RAINFALL"] == "AVAILABLE"
    assert twin.sensor_availability["SATELLITE"] == "AVAILABLE"
    assert twin.sensor_availability["RADAR"] == "UNAVAILABLE"
    assert twin.sensor_availability["LIGHTNING"] == "UNAVAILABLE"
    assert "radar_reflectivity" not in twin.current_features
    assert twin.current_features["infrared_brightness_temperature"] == 235.0
    assert twin.age_minutes == 60


def test_twin_acceleration_uses_successive_real_centroid_speeds():
    twin = build_multisensor_twin(_cell(), [])

    assert twin.acceleration_kmh_per_hour is not None
    assert twin.acceleration_kmh_per_hour > 0
    assert twin.acceleration_kmh_per_hour == pytest.approx(19.30, rel=0.04)
