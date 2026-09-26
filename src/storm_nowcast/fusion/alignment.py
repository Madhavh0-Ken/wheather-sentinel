from __future__ import annotations

import numpy as np
import xarray as xr


def align_gridded_variable(
    data: xr.DataArray,
    *,
    target_times: tuple[np.datetime64, ...],
    target_latitudes: tuple[float, ...],
    target_longitudes: tuple[float, ...],
    spatial_method: str,
    temporal_tolerance_minutes: int,
) -> xr.DataArray:
    required = {"time", "latitude", "longitude"}
    if not required.issubset(data.dims):
        raise ValueError(f"Gridded variables must contain dimensions {sorted(required)}")
    extra = set(data.dims) - required
    if extra:
        raise ValueError(f"Select vertical/channel dimensions before fusion: {sorted(extra)}")
    if spatial_method not in {"nearest", "linear"}:
        raise ValueError("spatial_method must be 'nearest' or 'linear'")
    ordered = data.transpose("time", "latitude", "longitude").sortby("time")
    temporal = ordered.reindex(
        time=np.asarray(target_times, dtype="datetime64[ns]"),
        method="nearest",
        tolerance=np.timedelta64(temporal_tolerance_minutes, "m"),
    )
    return temporal.interp(
        latitude=np.asarray(target_latitudes),
        longitude=np.asarray(target_longitudes),
        method=spatial_method,
    )
