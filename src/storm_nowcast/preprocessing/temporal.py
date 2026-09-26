from __future__ import annotations

import numpy as np
import xarray as xr


def validate_regular_time_steps(dataset: xr.Dataset, expected_minutes: int = 30) -> None:
    times = dataset.time.values.astype("datetime64[m]")
    if len(times) < 2:
        return
    deltas = np.diff(times).astype("timedelta64[m]").astype(int)
    if not np.all(deltas == expected_minutes):
        raise ValueError(f"Expected regular {expected_minutes}-minute observations")

