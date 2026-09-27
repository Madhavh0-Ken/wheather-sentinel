import gzip
from datetime import datetime, timezone

import numpy as np
import pytest

from storm_nowcast.config import Bounds
from storm_nowcast.data.rainfall import CmorphGridSpec, load_cmorph_file, parse_cmorph_bytes


TINY_GRID = CmorphGridSpec(
    nx=4,
    ny=3,
    lon_start=75.0,
    lon_step=1.0,
    lat_start=29.0,
    lat_step=1.0,
)


def test_parser_returns_two_regional_half_hour_frames_with_ascending_coordinates():
    values = np.arange(24, dtype="<f4").reshape(2, 3, 4)
    values[0, 1, 2] = -999.0

    ds = parse_cmorph_bytes(
        values.tobytes(),
        datetime(2023, 7, 9, 6, tzinfo=timezone.utc),
        Bounds(min_lat=30, max_lat=31, min_lon=76, max_lon=77),
        grid_spec=TINY_GRID,
    )

    assert ds.rain_rate.shape == (2, 2, 2)
    assert list(ds.latitude.values) == [30.0, 31.0]
    assert list(ds.longitude.values) == [76.0, 77.0]
    assert str(ds.time.values[1]) == "2023-07-09T06:30:00.000000000"
    assert np.isnan(ds.rain_rate.values[0, 0, 1])
    assert ds.missing_mask.values[0, 0, 1]
    assert ds.attrs["source_resolution"] == "~8 km grid spacing; effective source resolution is coarser"


def test_parser_rejects_wrong_binary_size():
    with pytest.raises(ValueError, match="expected 96 bytes"):
        parse_cmorph_bytes(
            b"truncated",
            datetime(2023, 7, 9, 6, tzinfo=timezone.utc),
            Bounds(min_lat=29, max_lat=31, min_lon=75, max_lon=77),
            grid_spec=TINY_GRID,
        )


def test_parser_rejects_dateline_crossing_bounds_explicitly():
    values = np.zeros((2, 3, 4), dtype="<f4")
    with pytest.raises(ValueError, match="dateline-crossing"):
        parse_cmorph_bytes(
            values.tobytes(),
            datetime(2023, 7, 9, 6, tzinfo=timezone.utc),
            Bounds.model_construct(min_lat=29, max_lat=31, min_lon=170, max_lon=-170),
            grid_spec=TINY_GRID,
        )


def test_parser_orders_non_dateline_region_across_greenwich():
    global_strip = CmorphGridSpec(
        nx=360,
        ny=1,
        lon_start=0.5,
        lon_step=1.0,
        lat_start=0.0,
        lat_step=1.0,
    )
    values = np.arange(720, dtype="<f4").reshape(2, 1, 360)

    dataset = parse_cmorph_bytes(
        values.tobytes(),
        datetime(2023, 7, 9, 6, tzinfo=timezone.utc),
        Bounds(min_lat=-0.5, max_lat=0.5, min_lon=-5.0, max_lon=5.0),
        grid_spec=global_strip,
    )

    assert dataset.longitude.values.tolist() == pytest.approx(
        [-4.5, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5, 4.5]
    )
    assert np.all(np.diff(dataset.longitude.values) > 0)


def test_loader_reads_historical_gzip_archive(tmp_path):
    values = np.arange(24, dtype="<f4").reshape(2, 3, 4)
    path = tmp_path / "historical.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(values.tobytes())

    ds = load_cmorph_file(
        path,
        datetime(2023, 7, 9, 6, tzinfo=timezone.utc),
        Bounds(min_lat=29, max_lat=31, min_lon=75, max_lon=77),
        grid_spec=TINY_GRID,
    )

    assert ds.rain_rate.shape == (2, 3, 3)
