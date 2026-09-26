from __future__ import annotations

import numpy as np
import xarray as xr


def validate_weather_dataset(dataset: xr.Dataset) -> xr.Dataset:
    required = {"rain_rate", "missing_mask"}
    missing_vars = required - set(dataset.data_vars)
    if missing_vars:
        raise ValueError(f"Dataset is missing variables: {sorted(missing_vars)}")
    for coordinate in ("time", "latitude", "longitude"):
        if coordinate not in dataset.coords:
            raise ValueError(f"Dataset is missing {coordinate} coordinate")
        values = dataset[coordinate].values
        if len(values) > 1 and not np.all(np.diff(values) > 0):
            raise ValueError(f"{coordinate} coordinate must be strictly ascending")
    if dataset.rain_rate.dims != ("time", "latitude", "longitude"):
        raise ValueError("rain_rate dimensions must be time, latitude, longitude")
    actual_missing = ~np.isfinite(dataset.rain_rate.values)
    if not np.array_equal(dataset.missing_mask.values.astype(bool), actual_missing):
        raise ValueError("missing_mask must exactly identify invalid rainfall observations")
    return dataset

