from __future__ import annotations

import bz2
import gzip
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.config import Bounds


@dataclass(frozen=True)
class CmorphGridSpec:
    nx: int = 4948
    ny: int = 1649
    lon_start: float = 0.036378335
    lon_step: float = 0.072756669
    lat_start: float = -59.963614
    lat_step: float = 0.072771377


CMORPH_GRID = CmorphGridSpec()


def parse_cmorph_bytes(
    payload: bytes,
    hour: datetime,
    bounds: Bounds,
    *,
    grid_spec: CmorphGridSpec = CMORPH_GRID,
) -> xr.Dataset:
    if hour.tzinfo is None or hour.utcoffset() is None:
        raise ValueError("CMORPH observation hour must be timezone-aware")
    if bounds.min_lon > bounds.max_lon:
        raise ValueError("dateline-crossing bounds are not supported")

    expected = 2 * grid_spec.ny * grid_spec.nx * 4
    if len(payload) != expected:
        raise ValueError(f"Invalid CMORPH payload: expected {expected} bytes, got {len(payload)}")

    values = np.frombuffer(payload, dtype="<f4").reshape(2, grid_spec.ny, grid_spec.nx)
    latitudes = grid_spec.lat_start + np.arange(grid_spec.ny) * grid_spec.lat_step
    source_lons = grid_spec.lon_start + np.arange(grid_spec.nx) * grid_spec.lon_step
    display_lons = ((source_lons + 180.0) % 360.0) - 180.0

    lat_mask = (latitudes >= bounds.min_lat) & (latitudes <= bounds.max_lat)
    lon_mask = (display_lons >= bounds.min_lon) & (display_lons <= bounds.max_lon)
    if not lat_mask.any() or not lon_mask.any():
        raise ValueError("Study-area bounds do not intersect the CMORPH grid")

    regional = values[:, lat_mask, :][:, :, lon_mask].astype(np.float32, copy=True)
    missing = (~np.isfinite(regional)) | (regional <= -900)
    regional[missing] = np.nan
    utc_hour = hour.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = np.array(
        [np.datetime64(utc_hour.replace(tzinfo=None), "ns"), np.datetime64((utc_hour + timedelta(minutes=30)).replace(tzinfo=None), "ns")]
    )

    return xr.Dataset(
        data_vars={
            "rain_rate": (("time", "latitude", "longitude"), regional, {"units": "mm hr-1"}),
            "missing_mask": (("time", "latitude", "longitude"), missing),
        },
        coords={
            "time": times,
            "latitude": latitudes[lat_mask],
            "longitude": display_lons[lon_mask],
        },
        attrs={
            "provider": "NOAA Climate Prediction Center",
            "product": "CMORPH V0.x RAW 8km-30min",
            "source_resolution": "~8 km grid spacing; effective source resolution is coarser",
            "crs": "EPSG:4326",
            "is_synthetic": False,
        },
    )


def load_cmorph_file(
    path: Path,
    hour: datetime,
    bounds: Bounds,
    *,
    grid_spec: CmorphGridSpec = CMORPH_GRID,
) -> xr.Dataset:
    opener = gzip.open if Path(path).suffix.lower() == ".gz" else bz2.open
    with opener(path, "rb") as handle:
        payload = handle.read()
    return parse_cmorph_bytes(payload, hour, bounds, grid_spec=grid_spec)
