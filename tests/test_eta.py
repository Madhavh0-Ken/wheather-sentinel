from datetime import timedelta

from storm_nowcast.eta.calculator import calculate_eta
from storm_nowcast.nowcast.motion import forecast_track
from tests.test_motion import moving_track


def test_eta_is_returned_when_moving_forecast_uncertainty_corridor_reaches_target():
    track = moving_track()
    forecasts = forecast_track(track)
    target = forecasts[1]

    result = calculate_eta(target.latitude, target.longitude, forecasts, track.last_seen)

    assert result.approaches_target is True
    assert result.closest_distance_km < 0.01
    assert result.closest_lead_minutes == 60
    assert result.estimated_arrival == track.last_seen + timedelta(minutes=60)
    assert result.uncertainty_km == target.uncertainty_km


def test_far_target_has_closest_approach_but_no_eta():
    track = moving_track()
    forecasts = forecast_track(track)

    result = calculate_eta(10.0, 10.0, forecasts, track.last_seen)

    assert result.approaches_target is False
    assert result.estimated_arrival is None
    assert result.closest_distance_km > 1000
    assert "outside" in result.explanation


def test_stationary_forecast_never_claims_exact_arrival_even_inside_uncertainty():
    track = moving_track(speed=0, bearing=None)
    forecasts = forecast_track(track)

    result = calculate_eta(
        track.current.centroid_lat,
        track.current.centroid_lon,
        forecasts,
        track.last_seen,
    )

    assert result.approaches_target is True
    assert result.estimated_arrival is None
    assert "insufficient motion evidence" in result.explanation.lower()
