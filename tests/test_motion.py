from datetime import datetime, timedelta, timezone

import pytest

from storm_nowcast.models.schemas import CellObservation, StormCell
from storm_nowcast.nowcast.motion import forecast_track
from storm_nowcast.tracking.tracker import haversine_km


def moving_track(speed=60.0, bearing=90.0):
    start = datetime(2023, 7, 9, 0, tzinfo=timezone.utc)
    observations = [
        CellObservation(
            timestamp=start,
            centroid_lat=30.0,
            centroid_lon=75.0,
            area_km2=100,
            max_intensity=25,
            mean_intensity=20,
            bbox=(29.95, 74.95, 30.05, 75.05),
            polygon_geojson={"type": "Polygon", "coordinates": []},
        ),
        CellObservation(
            timestamp=start + timedelta(minutes=30),
            centroid_lat=30.0,
            centroid_lon=75.31,
            area_km2=110,
            max_intensity=30,
            mean_intensity=25,
            bbox=(29.95, 75.26, 30.05, 75.36),
            polygon_geojson={"type": "Polygon", "coordinates": []},
        ),
    ]
    return StormCell(
        id="IPC-001",
        history=observations,
        speed_kmh=speed,
        bearing_deg=bearing,
        intensity_trend_mm_hr_per_hour=10,
        growth_trend_km2_per_hour=20,
        first_seen=start,
        last_seen=start + timedelta(minutes=30),
        is_synthetic=True,
    )


def test_forecast_uses_exact_leads_geodesic_distance_and_growing_uncertainty():
    track = moving_track()
    forecasts = forecast_track(track)

    assert [point.lead_minutes for point in forecasts] == [30, 60, 120]
    assert haversine_km(30.0, 75.31, forecasts[1].latitude, forecasts[1].longitude) == pytest.approx(60, rel=0.01)
    assert forecasts[0].valid_at == track.last_seen + timedelta(minutes=30)
    assert forecasts[0].uncertainty_km < forecasts[1].uncertainty_km < forecasts[2].uncertainty_km
    assert forecasts[2].confidence == "LOW"


def test_stationary_track_stays_in_place_but_uncertainty_still_grows():
    track = moving_track(speed=0, bearing=None)
    forecasts = forecast_track(track)

    assert all(point.latitude == pytest.approx(track.current.centroid_lat) for point in forecasts)
    assert all(point.longitude == pytest.approx(track.current.centroid_lon) for point in forecasts)
    assert forecasts[0].uncertainty_km < forecasts[-1].uncertainty_km
    assert all(point.confidence == "LOW" for point in forecasts)
