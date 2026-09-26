from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.manual import PointObservationProduct, load_explicit_point_csv
from storm_nowcast.data.sources import ImdLightningSource
from storm_nowcast.models.sensors import SourceDescriptor


IMD_LIGHTNING_DESCRIPTOR = SourceDescriptor(
    provider="India Meteorological Department",
    product="User-selected official lightning event product",
    sensor="LIGHTNING",
    official_url="https://mausam.imd.gov.in/",
    access_method="official manual import; exact access route must be supplied by the user",
    authentication_required=True,
)


def load_imd_lightning_file(
    path: Path,
    *,
    column_map: dict[str, str],
    bounds: Bounds,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> PointObservationProduct:
    return load_explicit_point_csv(
        path,
        source=IMD_LIGHTNING_DESCRIPTOR,
        column_map=column_map,
        bounds=bounds,
        is_synthetic=is_synthetic,
        confirmed_official_origin=confirmed_official_origin,
    )


def grid_lightning_windows(
    events: pd.DataFrame,
    *,
    valid_at: datetime,
    latitude_edges: list[float],
    longitude_edges: list[float],
    windows: tuple[int, ...] = (5, 10, 30),
) -> xr.Dataset:
    valid_at = pd.Timestamp(valid_at)
    if valid_at.tzinfo is None:
        raise ValueError("valid_at must be timezone-aware")
    latitude_edges_array = np.asarray(latitude_edges, dtype=float)
    longitude_edges_array = np.asarray(longitude_edges, dtype=float)
    output = xr.Dataset(
        coords={
            "latitude": (latitude_edges_array[:-1] + latitude_edges_array[1:]) / 2,
            "longitude": (longitude_edges_array[:-1] + longitude_edges_array[1:]) / 2,
        }
    )
    for minutes in windows:
        start = valid_at - timedelta(minutes=minutes)
        selected = events.loc[(events.timestamp > start) & (events.timestamp <= valid_at)]
        counts, _, _ = np.histogram2d(
            selected.latitude,
            selected.longitude,
            bins=(latitude_edges_array, longitude_edges_array),
        )
        name = f"lightning_count_{minutes}min"
        output[name] = (("latitude", "longitude"), counts.astype(int))
        output[name].attrs.update(
            {
                "units": "count",
                "variable_status": "OBSERVED",
                "aggregation_window_minutes": minutes,
                "provider": "India Meteorological Department",
            }
        )
    output.attrs.update({"valid_at": valid_at.isoformat(), "variable_status": "OBSERVED"})
    return output

__all__ = ["ImdLightningSource", "load_imd_lightning_file", "grid_lightning_windows"]
