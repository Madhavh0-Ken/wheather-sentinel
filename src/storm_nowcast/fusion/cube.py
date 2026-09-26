from __future__ import annotations

import json
from typing import Literal

import numpy as np
import xarray as xr
from pydantic import BaseModel, Field, model_validator

from storm_nowcast.data.manual import IngestedProduct
from storm_nowcast.fusion.alignment import align_gridded_variable


class TargetGridSpec(BaseModel):
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    resolution_km: float = Field(gt=0)
    crs: str = "EPSG:4326"

    @model_validator(mode="after")
    def validate_coordinates(self) -> "TargetGridSpec":
        if len(self.latitudes) < 1 or len(self.longitudes) < 1:
            raise ValueError("Target grid coordinates cannot be empty")
        if tuple(sorted(set(self.latitudes))) != self.latitudes:
            raise ValueError("Target latitudes must be unique and increasing")
        if tuple(sorted(set(self.longitudes))) != self.longitudes:
            raise ValueError("Target longitudes must be unique and increasing")
        return self


class ResamplingPolicy(BaseModel):
    spatial_method: Literal["nearest", "linear"] = "nearest"
    temporal_tolerance_minutes: int = Field(default=15, ge=0, le=360)


def _variable_attrs(product: IngestedProduct, variable: str, grid: TargetGridSpec, policy: ResamplingPolicy) -> dict:
    lineage = product.lineage[variable]
    native_km = lineage.native_spatial_resolution.grid_spacing_km
    attrs = {
        "provider": product.asset.source.provider,
        "product": product.asset.source.product,
        "variable_status": lineage.status,
        "units": lineage.processed_units,
        "source_record_ids": json.dumps(lineage.source_record_ids),
        "native_spatial_resolution_km": native_km,
        "native_resolution_description": lineage.native_spatial_resolution.native_description or "",
        "effective_resolution_note": lineage.native_spatial_resolution.effective_resolution_note or "",
        "analysis_grid_resolution_km": grid.resolution_km,
        "resampling_method": policy.spatial_method,
        "temporal_tolerance_minutes": policy.temporal_tolerance_minutes,
        "is_synthetic": product.asset.is_synthetic,
    }
    if native_km is not None and grid.resolution_km < native_km:
        attrs["physical_resolution_warning"] = (
            f"Resampling a {native_km:g} km native grid onto a {grid.resolution_km:g} km analysis grid "
            f"does not create {grid.resolution_km:.1f} km physical observations."
        )
    return attrs


def build_weather_cube(
    products: list[IngestedProduct],
    *,
    grid: TargetGridSpec,
    target_times: tuple[np.datetime64, ...],
    policies: dict[str, ResamplingPolicy] | None = None,
) -> xr.Dataset:
    policies = policies or {}
    times = np.asarray(target_times, dtype="datetime64[ns]")
    if times.size == 0 or np.any(times[1:] <= times[:-1]):
        raise ValueError("target_times must be non-empty, unique, and increasing")
    cube = xr.Dataset(
        coords={
            "time": times,
            "y": np.arange(len(grid.latitudes)),
            "x": np.arange(len(grid.longitudes)),
            "latitude": ("y", np.asarray(grid.latitudes)),
            "longitude": ("x", np.asarray(grid.longitudes)),
        },
        attrs={
            "crs": grid.crs,
            "analysis_grid_resolution_km": grid.resolution_km,
            "source_count": len(products),
        },
    )
    seen: set[str] = set()
    for product in products:
        for variable in product.lineage:
            if variable in seen:
                raise ValueError(f"Duplicate cube variable {variable}; choose an explicit source priority")
            seen.add(variable)
            policy = policies.get(variable, ResamplingPolicy())
            aligned = align_gridded_variable(
                product.dataset[variable],
                target_times=target_times,
                target_latitudes=grid.latitudes,
                target_longitudes=grid.longitudes,
                spatial_method=policy.spatial_method,
                temporal_tolerance_minutes=policy.temporal_tolerance_minutes,
            )
            cube[variable] = (("time", "y", "x"), np.asarray(aligned.values))
            cube[variable].attrs.update(_variable_attrs(product, variable, grid, policy))
            mask_name = f"{variable}__missing"
            cube[mask_name] = (("time", "y", "x"), ~np.isfinite(np.asarray(aligned.values)))
            cube[mask_name].attrs.update(
                {
                    "variable_status": "DERIVED",
                    "meaning": f"True where {variable} is unavailable after explicit alignment",
                    "source_variable": variable,
                }
            )
    return cube
