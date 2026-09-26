from datetime import datetime, timezone

import pandas as pd
import pytest

from storm_nowcast.config import Bounds
from storm_nowcast.data.lightning import grid_lightning_windows, load_imd_lightning_file
from storm_nowcast.data.stations import load_imd_station_file


def test_lightning_csv_uses_explicit_columns_and_keeps_only_real_optional_fields(tmp_path):
    path = tmp_path / "synthetic_lightning.csv"
    pd.DataFrame(
        {
            "when": ["2023-07-09T00:01:00Z", "2023-07-09T00:08:00Z"],
            "lat": [31.0, 31.1],
            "lon": [77.0, 77.1],
            "reported_type": ["CG", "IC"],
        }
    ).to_csv(path, index=False)

    events = load_imd_lightning_file(
        path,
        column_map={"timestamp": "when", "latitude": "lat", "longitude": "lon", "type": "reported_type"},
        bounds=Bounds(min_lat=30, max_lat=32, min_lon=76, max_lon=78),
        is_synthetic=True,
    )

    assert list(events.frame.columns) == ["timestamp", "latitude", "longitude", "type"]
    assert str(events.frame.timestamp.dt.tz) == "UTC"
    assert "quality" not in events.frame
    assert events.asset.is_synthetic is True


def test_lightning_window_counts_are_observed_and_time_bounded(tmp_path):
    path = tmp_path / "synthetic_lightning.csv"
    pd.DataFrame(
        {
            "t": [
                "2023-07-09T00:01:00Z",
                "2023-07-09T00:06:00Z",
                "2023-07-09T00:08:00Z",
                "2023-07-09T00:19:00Z",
            ],
            "y": [31.0, 31.0, 31.0, 31.0],
            "x": [77.0, 77.0, 77.0, 77.0],
        }
    ).to_csv(path, index=False)
    events = load_imd_lightning_file(
        path,
        column_map={"timestamp": "t", "latitude": "y", "longitude": "x"},
        bounds=Bounds(min_lat=30, max_lat=32, min_lon=76, max_lon=78),
        is_synthetic=True,
    )

    features = grid_lightning_windows(
        events.frame,
        valid_at=datetime(2023, 7, 9, 0, 10, tzinfo=timezone.utc),
        latitude_edges=[30.0, 32.0],
        longitude_edges=[76.0, 78.0],
        windows=(5, 10, 30),
    )

    assert features.lightning_count_5min.item() == 2
    assert features.lightning_count_10min.item() == 3
    assert features.lightning_count_30min.item() == 3
    assert features.lightning_count_5min.attrs["variable_status"] == "OBSERVED"


def test_station_loader_does_not_invent_unmapped_variables(tmp_path):
    path = tmp_path / "synthetic_station.csv"
    pd.DataFrame(
        {"time": ["2023-07-09T00:00:00Z"], "lat": [31.0], "lon": [77.0], "temp": [22.5], "mystery": [99]}
    ).to_csv(path, index=False)

    observations = load_imd_station_file(
        path,
        column_map={"timestamp": "time", "latitude": "lat", "longitude": "lon", "temperature": "temp"},
        units={"temperature": "degC"},
        bounds=Bounds(min_lat=30, max_lat=32, min_lon=76, max_lon=78),
        is_synthetic=True,
    )

    assert list(observations.frame.columns) == ["timestamp", "latitude", "longitude", "temperature"]
    assert observations.units == {"temperature": "degC"}
    assert "mystery" not in observations.frame


def test_point_loader_rejects_incomplete_mapping(tmp_path):
    path = tmp_path / "events.csv"
    pd.DataFrame({"t": [], "lat": []}).to_csv(path, index=False)

    with pytest.raises(ValueError, match="timestamp, latitude, and longitude"):
        load_imd_lightning_file(
            path,
            column_map={"timestamp": "t", "latitude": "lat"},
            bounds=Bounds(min_lat=30, max_lat=32, min_lon=76, max_lon=78),
            is_synthetic=True,
        )
