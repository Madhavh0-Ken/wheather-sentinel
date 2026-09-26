from __future__ import annotations

import xarray as xr

from storm_nowcast.config import Bounds


def subset_geographic(dataset: xr.Dataset, bounds: Bounds) -> xr.Dataset:
    subset = dataset.sel(
        latitude=slice(bounds.min_lat, bounds.max_lat),
        longitude=slice(bounds.min_lon, bounds.max_lon),
    )
    if not subset.sizes.get("latitude") or not subset.sizes.get("longitude"):
        raise ValueError("Study-area bounds do not intersect the dataset")
    return subset

