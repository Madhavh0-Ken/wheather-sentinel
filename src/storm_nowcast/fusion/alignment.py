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
    temporal_method: str = "nearest",
) -> xr.DataArray:
    required = {"time", "latitude", "longitude"}
    if not required.issubset(data.dims):
        raise ValueError(f"Gridded variables must contain dimensions {sorted(required)}")
    extra = set(data.dims) - required
    if extra:
        raise ValueError(f"Select vertical/channel dimensions before fusion: {sorted(extra)}")
    if spatial_method not in {"nearest", "linear"}:
        raise ValueError("spatial_method must be 'nearest' or 'linear'")
    if temporal_method not in {"nearest", "backward"}:
        raise ValueError("temporal_method must be 'nearest' or 'backward'")
    ordered = data.transpose("time", "latitude", "longitude").sortby("time")
    ordered = ordered.assign_coords(
        source_observation_time=("time", ordered.time.values.astype("datetime64[ns]"))
    )
    targets = np.asarray(target_times, dtype="datetime64[ns]")
    temporal = ordered.reindex(
        time=targets,
        method="pad" if temporal_method == "backward" else "nearest",
        tolerance=np.timedelta64(temporal_tolerance_minutes, "m"),
    )
    selected = temporal.source_observation_time.values.astype("datetime64[ns]")
    available = ~np.isnat(selected)
    ages = np.full(targets.shape, np.nan, dtype=float)
    ages[available] = (targets[available] - selected[available]) / np.timedelta64(1, "m")
    temporal = temporal.assign_coords(
        source_available=("time", available),
        source_age_minutes=("time", ages),
    )
    return temporal.interp(
        latitude=np.asarray(target_latitudes),
        longitude=np.asarray(target_longitudes),
        method=spatial_method,
    )
