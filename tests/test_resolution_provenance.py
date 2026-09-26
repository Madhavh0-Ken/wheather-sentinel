import json
import numpy as np

from storm_nowcast.fusion.cube import TargetGridSpec, build_weather_cube
from storm_nowcast.preprocessing.metadata import validate_resolution_claims
from tests.test_weather_cube import _satellite_product


def test_resampled_variable_exposes_native_and_analysis_resolution_warning(tmp_path):
    product = _satellite_product(tmp_path)
    cube = build_weather_cube(
        [product],
        grid=TargetGridSpec(latitudes=(30.0, 31.0), longitudes=(76.0, 77.0), resolution_km=3.0),
        target_times=(np.datetime64("2023-07-09T00:00:00"),),
    )
    attrs = cube.infrared_brightness_temperature.attrs

    assert attrs["native_spatial_resolution_km"] == 8.0
    assert attrs["analysis_grid_resolution_km"] == 3.0
    assert attrs["resampling_method"] == "nearest"
    assert "does not create 3.0 km physical observations" in attrs["physical_resolution_warning"]
    assert json.loads(attrs["source_record_ids"])[0].startswith("sha256:")
    validate_resolution_claims(cube)


def test_resolution_validator_rejects_false_native_resolution_claim(tmp_path):
    product = _satellite_product(tmp_path)
    cube = build_weather_cube(
        [product],
        grid=TargetGridSpec(latitudes=(30.0, 31.0), longitudes=(76.0, 77.0), resolution_km=3.0),
        target_times=(np.datetime64("2023-07-09T00:00:00"),),
    )
    cube.infrared_brightness_temperature.attrs.pop("native_spatial_resolution_km")

    import pytest

    with pytest.raises(ValueError, match="native_spatial_resolution_km"):
        validate_resolution_claims(cube)
