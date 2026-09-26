from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from storm_nowcast.config import DetectionConfig
from storm_nowcast.detection.storms import detect_cells


def test_detection_segments_thresholded_cells_and_calculates_statistics():
    field = xr.DataArray(
        np.array(
            [
                [12.0, 20.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 40.0],
            ],
            dtype=np.float32,
        ),
        dims=("latitude", "longitude"),
        coords={"latitude": [30.0, 31.0, 32.0], "longitude": [75.0, 76.0, 77.0, 78.0]},
        attrs={"is_synthetic": True},
    )

    cells = detect_cells(
        field,
        datetime(2023, 7, 9, tzinfo=timezone.utc),
        DetectionConfig(threshold_mm_hr=10.0, minimum_pixels=2),
    )

    assert len(cells) == 1
    cell = cells[0]
    assert cell.pixel_count == 2
    assert cell.max_intensity == 20.0
    assert cell.mean_intensity == 16.0
    assert cell.centroid_lat == pytest.approx(30.0)
    assert cell.centroid_lon == pytest.approx(75.625)
    assert cell.bbox == pytest.approx((29.5, 74.5, 30.5, 76.5))
    assert cell.area_km2 > 20_000
    assert cell.polygon_geojson["type"] in {"Polygon", "MultiPolygon"}
    assert cell.is_synthetic is True


def test_detection_ignores_nan_and_below_threshold_values():
    field = xr.DataArray(
        [[np.nan, 9.99], [0.0, 10.0]],
        dims=("latitude", "longitude"),
        coords={"latitude": [30.0, 30.1], "longitude": [75.0, 75.1]},
    )

    cells = detect_cells(
        field,
        datetime(2023, 7, 9, tzinfo=timezone.utc),
        DetectionConfig(threshold_mm_hr=10.0, minimum_pixels=2),
    )

    assert cells == []
