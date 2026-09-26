import numpy as np
import pytest
import xarray as xr

from storm_nowcast.preprocessing.grid import grid_cell_area_km2
from storm_nowcast.preprocessing.validation import validate_weather_dataset


def _dataset(latitudes=(30.0, 31.0), longitudes=(75.0, 76.0)):
    rain = np.array([[[1.0, np.nan], [2.0, 3.0]]], dtype=np.float32)
    return xr.Dataset(
        {
            "rain_rate": (("time", "latitude", "longitude"), rain),
            "missing_mask": (("time", "latitude", "longitude"), np.isnan(rain)),
        },
        coords={
            "time": [np.datetime64("2023-07-09T00:00")],
            "latitude": list(latitudes),
            "longitude": list(longitudes),
        },
        attrs={"is_synthetic": True},
    )


def test_validation_accepts_ascending_grid_and_consistent_missing_mask():
    validated = validate_weather_dataset(_dataset())

    assert validated.sizes == {"time": 1, "latitude": 2, "longitude": 2}


def test_validation_rejects_descending_coordinates():
    with pytest.raises(ValueError, match="strictly ascending"):
        validate_weather_dataset(_dataset(latitudes=(31.0, 30.0)))


def test_validation_rejects_missing_mask_that_hides_valid_data():
    ds = _dataset()
    ds["missing_mask"].values[0, 0, 0] = True
    with pytest.raises(ValueError, match="missing_mask"):
        validate_weather_dataset(ds)


def test_grid_cell_area_shrinks_toward_higher_latitude():
    equatorial = grid_cell_area_km2(0.0, 0.1, 0.1)
    northern = grid_cell_area_km2(60.0, 0.1, 0.1)

    assert 120 < equatorial < 125
    assert northern < equatorial * 0.55
