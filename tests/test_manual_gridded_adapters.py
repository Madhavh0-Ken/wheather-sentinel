from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.radar import load_imd_radar_file
from storm_nowcast.data.satellite import derive_satellite_evolution, load_mosdac_file
from storm_nowcast.models.sensors import SpatialResolution


def _write_grid(path, variable, values, units):
    dataset = xr.Dataset(
        {variable: (("time", "latitude", "longitude"), np.asarray([values], dtype=float))},
        coords={
            "time": [np.datetime64("2023-07-09T00:00:00")],
            "latitude": [32.0, 31.0, 30.0],
            "longitude": [75.0, 76.0, 77.0],
        },
        attrs={"is_synthetic": 1, "time_coverage_start": "2023-07-09T00:00:00Z"},
    )
    dataset[variable].attrs.update({"units": units, "_FillValue": -999.0})
    dataset.to_netcdf(path, engine="h5netcdf")


def test_mosdac_loader_requires_explicit_channel_map_and_preserves_native_metadata(tmp_path):
    path = tmp_path / "synthetic_insat.h5"
    _write_grid(path, "TIR_TEST", [[280, 279, 278], [277, -999, 275], [274, 273, 272]], "K")

    product = load_mosdac_file(
        path,
        bounds=Bounds(min_lat=30.5, max_lat=32.5, min_lon=75.5, max_lon=77.5),
        variable_map={"infrared_brightness_temperature": "TIR_TEST"},
        native_resolution=SpatialResolution(grid_spacing_km=4.0),
        is_synthetic=True,
    )

    assert list(product.dataset.data_vars) == ["infrared_brightness_temperature"]
    assert product.dataset.latitude.values.tolist() == [31.0, 32.0]
    assert product.dataset.longitude.values.tolist() == [76.0, 77.0]
    assert np.isnan(product.dataset.infrared_brightness_temperature.sel(latitude=31, longitude=76))
    lineage = product.lineage["infrared_brightness_temperature"]
    assert lineage.native_units == "K"
    assert lineage.native_spatial_resolution.grid_spacing_km == 4.0
    assert lineage.status == "OBSERVED"
    assert product.asset.is_synthetic is True


def test_mosdac_loader_does_not_guess_unknown_channel(tmp_path):
    path = tmp_path / "synthetic_insat.nc"
    _write_grid(path, "MYSTERY", [[1, 2, 3], [4, 5, 6], [7, 8, 9]], "1")

    with pytest.raises(ValueError, match="explicit variable_map"):
        load_mosdac_file(
            path,
            bounds=Bounds(min_lat=29, max_lat=33, min_lon=74, max_lon=78),
            variable_map={},
            native_resolution=SpatialResolution(grid_spacing_km=4.0),
            is_synthetic=True,
        )


def test_satellite_evolution_derives_cooling_only_from_kelvin_observations(tmp_path):
    first_path = tmp_path / "first.nc"
    second_path = tmp_path / "second.nc"
    _write_grid(first_path, "BT", [[250, 250, 260], [260, 260, 260], [260, 260, 260]], "K")
    _write_grid(second_path, "BT", [[245, 245, 250], [260, 260, 260], [260, 260, 260]], "K")
    bounds = Bounds(min_lat=29, max_lat=33, min_lon=74, max_lon=78)
    kwargs = dict(
        bounds=bounds,
        variable_map={"infrared_brightness_temperature": "BT"},
        native_resolution=SpatialResolution(grid_spacing_km=4.0),
        is_synthetic=True,
    )
    first = load_mosdac_file(first_path, **kwargs)
    second = load_mosdac_file(second_path, **kwargs)
    second.dataset["time"] = [np.datetime64("2023-07-09T00:30:00")]

    evolution = derive_satellite_evolution(first, second, cold_threshold_k=255.0)

    assert evolution.cloud_top_cooling_rate_k_per_hour.sel(latitude=32, longitude=75).item() == 10.0
    assert evolution.attrs["variable_status"] == "DERIVED"
    assert evolution.attrs["cold_cloud_expansion_fraction_per_hour"] == pytest.approx(2 / 9)


def test_imd_radar_loader_maps_only_user_identified_reflectivity(tmp_path):
    path = tmp_path / "synthetic_radar.nc"
    _write_grid(path, "DBZ_TEST", [[10, 20, 30], [15, 25, 35], [5, 10, 15]], "dBZ")

    product = load_imd_radar_file(
        path,
        bounds=Bounds(min_lat=29, max_lat=33, min_lon=74, max_lon=78),
        variable_map={"radar_reflectivity": "DBZ_TEST"},
        native_resolution=SpatialResolution(grid_spacing_km=1.0),
        is_synthetic=True,
    )

    assert product.dataset.radar_reflectivity.attrs["units"] == "dBZ"
    assert product.lineage["radar_reflectivity"].native_spatial_resolution.grid_spacing_km == 1.0


def test_manual_production_asset_requires_explicit_origin_confirmation(tmp_path):
    path = tmp_path / "unconfirmed.nc"
    _write_grid(path, "BT", [[250, 250, 250], [250, 250, 250], [250, 250, 250]], "K")

    with pytest.raises(ValueError, match="confirmed_official_origin"):
        load_mosdac_file(
            path,
            bounds=Bounds(min_lat=29, max_lat=33, min_lon=74, max_lon=78),
            variable_map={"infrared_brightness_temperature": "BT"},
            native_resolution=SpatialResolution(grid_spacing_km=4.0),
        )
