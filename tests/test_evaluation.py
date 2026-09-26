from datetime import datetime, timedelta, timezone

from storm_nowcast.evaluation import evaluate_forecasts
from storm_nowcast.models.schemas import CellObservation, ForecastPoint, StormCell


def observation(time, lat, lon):
    return CellObservation(
        timestamp=time,
        centroid_lat=lat,
        centroid_lon=lon,
        area_km2=100,
        max_intensity=20,
        mean_intensity=15,
        bbox=(lat - 0.05, lon - 0.05, lat + 0.05, lon + 0.05),
        polygon_geojson={
            "type": "Polygon",
            "coordinates": [[
                [lon - 0.05, lat - 0.05], [lon + 0.05, lat - 0.05],
                [lon + 0.05, lat + 0.05], [lon - 0.05, lat + 0.05],
                [lon - 0.05, lat - 0.05],
            ]],
        },
    )


def test_evaluation_calculates_real_position_error_iou_and_continuity():
    issued = datetime(2023, 7, 9, tzinfo=timezone.utc)
    current = observation(issued, 30, 75)
    forecast = ForecastPoint(
        lead_minutes=30,
        valid_at=issued + timedelta(minutes=30),
        latitude=30,
        longitude=75.1,
        uncertainty_km=20,
        confidence="MEDIUM",
    )
    issued_track = StormCell(
        id="IPC-001", history=[current], first_seen=issued, last_seen=issued, forecasts=[forecast]
    )
    actual = observation(issued + timedelta(minutes=30), 30, 75.11)
    later_track = StormCell(
        id="IPC-001", history=[current, actual], first_seen=issued, last_seen=actual.timestamp
    )

    metrics = evaluate_forecasts([issued_track], [later_track])

    assert len(metrics) == 1
    assert 0.9 < metrics[0].position_error_km < 1.1
    assert 0 < metrics[0].iou < 1
    assert metrics[0].track_continuity == 1.0
    assert metrics[0].sample_count == 1


def test_evaluation_reports_insufficient_observations_instead_of_inventing_metric():
    issued = datetime(2023, 7, 9, tzinfo=timezone.utc)
    issued_track = StormCell(
        id="IPC-001", history=[observation(issued, 30, 75)], first_seen=issued, last_seen=issued
    )

    metrics = evaluate_forecasts([issued_track], [])

    assert len(metrics) == 1
    assert metrics[0].position_error_km is None
    assert metrics[0].message == "Insufficient observations for validated metric."
