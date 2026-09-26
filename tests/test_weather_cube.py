import numpy as np
import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.satellite import load_mosdac_file
from storm_nowcast.fusion.cube import ResamplingPolicy, TargetGridSpec, build_weather_cube
from storm_nowcast.models.sensors import SpatialResolution


def _satellite_product(tmp_path):
    path = tmp_path / "satellite.nc"
    dataset = xr.Dataset(
        {"BT": (("time", "latitude", "longitude"), [[[250.0, 252.0], [254.0, np.nan]]])},
        coords={
            "time": [np.datetime64("2023-07-09T00:00:00")],
            "latitude": [30.0, 31.0],
            "longitude": [76.0, 77.0],
        },
    )
    dataset.BT.attrs["units"] = "K"
    dataset.to_netcdf(path, engine="h5netcdf")
    return load_mosdac_file(
        path,
        bounds=Bounds(min_lat=29, max_lat=32, min_lon=75, max_lon=78),
        variable_map={"infrared_brightness_temperature": "BT"},
        native_resolution=SpatialResolution(grid_spacing_km=8.0, effective_resolution_note="coarser effective resolution"),
        is_synthetic=True,
    )


def test_weather_cube_aligns_available_variables_to_time_y_x_and_keeps_missing_mask(tmp_path):
    product = _satellite_product(tmp_path)
    grid = TargetGridSpec(
        latitudes=(30.0, 30.5, 31.0),
        longitudes=(76.0, 76.5, 77.0),
        resolution_km=3.0,
    )

    cube = build_weather_cube(
        [product],
        grid=grid,
        target_times=(np.datetime64("2023-07-09T00:00:00"),),
        policies={"infrared_brightness_temperature": ResamplingPolicy(spatial_method="nearest")},
    )

    assert cube.sizes == {"time": 1, "y": 3, "x": 3}
    assert cube.latitude.dims == ("y",)
    assert cube.longitude.dims == ("x",)
    assert "infrared_brightness_temperature" in cube
    assert "infrared_brightness_temperature__missing" in cube
    assert cube.infrared_brightness_temperature__missing.dtype == bool
    assert bool(cube.infrared_brightness_temperature__missing.isel(time=0, y=2, x=2)) is True
    assert "radar_reflectivity" not in cube


def test_weather_cube_temporal_tolerance_does_not_reuse_stale_scan(tmp_path):
    product = _satellite_product(tmp_path)
    grid = TargetGridSpec(latitudes=(30.0, 31.0), longitudes=(76.0, 77.0), resolution_km=3.0)

    cube = build_weather_cube(
        [product],
        grid=grid,
        target_times=(np.datetime64("2023-07-09T00:00:00"), np.datetime64("2023-07-09T00:30:00")),
        policies={
            "infrared_brightness_temperature": ResamplingPolicy(
                spatial_method="nearest", temporal_tolerance_minutes=10
            )
        },
    )

    assert cube.infrared_brightness_temperature.isel(time=0).notnull().any()
    assert cube.infrared_brightness_temperature.isel(time=1).isnull().all()


def test_weather_cube_rejects_duplicate_canonical_variables(tmp_path):
    product = _satellite_product(tmp_path)
    grid = TargetGridSpec(latitudes=(30.0, 31.0), longitudes=(76.0, 77.0), resolution_km=3.0)

    import pytest

    with pytest.raises(ValueError, match="Duplicate cube variable"):
        build_weather_cube(
            [product, product],
            grid=grid,
            target_times=(np.datetime64("2023-07-09T00:00:00"),),
        )
