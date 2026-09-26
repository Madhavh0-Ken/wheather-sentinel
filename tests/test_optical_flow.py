from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import xarray as xr

from storm_nowcast.nowcast.optical_flow import estimate_translation, forecast_rainfall_fields
from tests.test_motion import moving_track


def _field(values, at):
    return xr.DataArray(
        np.asarray(values, dtype=float),
        dims=("latitude", "longitude"),
        coords={"latitude": np.arange(len(values)), "longitude": np.arange(len(values[0]))},
        attrs={"timestamp": at.isoformat()},
    )


def test_translation_and_advection_use_exact_short_range_leads():
    at = datetime(2023, 7, 9, tzinfo=timezone.utc)
    previous = np.zeros((12, 12))
    current = np.zeros((12, 12))
    previous[5:7, 4:6] = 20
    current[5:7, 5:7] = 20
    first = _field(previous, at)
    second = _field(current, at + timedelta(minutes=10))

    motion = estimate_translation(first, second, delta_minutes=10)
    product = forecast_rainfall_fields(first, second, issued_at=at + timedelta(minutes=10))

    assert motion.shift_y_pixels == pytest.approx(0, abs=0.1)
    assert motion.shift_x_pixels == pytest.approx(1, abs=0.1)
    assert [field.lead_minutes for field in product.fields] == [10, 20, 30, 60, 90, 120]
    assert [field.uncertainty_km for field in product.fields] == sorted(
        field.uncertainty_km for field in product.fields
    )
    assert product.method == "phase-correlation translation advection"
    first_forecast = product.fields[0].rain_rate
    assert np.unravel_index(np.nanargmax(first_forecast.values), first_forecast.shape)[1] in {6, 7}


def test_growth_projection_is_bounded_instead_of_exploding():
    at = datetime(2023, 7, 9, tzinfo=timezone.utc)
    previous = np.ones((8, 8))
    current = np.full((8, 8), 10.0)

    product = forecast_rainfall_fields(
        _field(previous, at),
        _field(current, at + timedelta(minutes=10)),
        issued_at=at + timedelta(minutes=10),
    )

    assert max(float(field.rain_rate.max()) for field in product.fields) <= 15.0
    assert min(float(field.rain_rate.min()) for field in product.fields) >= 0.0


def test_missing_coverage_falls_back_to_existing_deterministic_track():
    at = datetime(2023, 7, 9, tzinfo=timezone.utc)
    sparse = np.full((8, 8), np.nan)
    sparse[0, 0] = 10

    product = forecast_rainfall_fields(
        _field(sparse, at),
        _field(sparse, at + timedelta(minutes=10)),
        issued_at=at + timedelta(minutes=10),
        deterministic_cell=moving_track(),
    )

    assert product.fallback_used is True
    assert product.fields == []
    assert [point.lead_minutes for point in product.point_forecasts] == [10, 20, 30, 60, 90, 120]
    assert "finite coverage" in product.fallback_reason.lower()
