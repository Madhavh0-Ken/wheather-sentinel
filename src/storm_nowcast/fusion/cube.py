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
    temporal_method: Literal["nearest", "backward"] = "nearest"


def _variable_attrs(
    product: IngestedProduct,
    variable: str,
    grid: TargetGridSpec,
    policy: ResamplingPolicy,
    *,
    source_record_ids: list[str] | None = None,
) -> dict:
    lineage = product.lineage[variable]
    native_km = lineage.native_spatial_resolution.grid_spacing_km
    attrs = {
        "provider": product.asset.source.provider,
        "product": product.asset.source.product,
        "variable_status": lineage.status,
        "units": lineage.processed_units,
        "source_record_ids": json.dumps(source_record_ids or lineage.source_record_ids),
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


def _metadata_value(value: object) -> str:
    if value is None or (isinstance(value, (float, np.floating)) and np.isnan(value)):
        return ""
    return str(value)


def _combined_variable(
    entries: list[tuple[IngestedProduct, xr.DataArray]],
    variable: str,
) -> tuple[IngestedProduct, xr.DataArray, list[str]]:
    first_product = entries[0][0]
    descriptors = [item.asset.source.model_dump() for item, _ in entries]
    if any(descriptor != descriptors[0] for descriptor in descriptors[1:]):
        raise ValueError(f"Duplicate cube variable {variable}; choose an explicit source priority")

    arrays: list[xr.DataArray] = []
    source_record_ids: list[str] = []
    source_times: list[np.datetime64] = []
    for product, data in entries:
        lineage = product.lineage[variable]
        source_record_ids.extend(lineage.source_record_ids)
        values = data
        count = values.sizes["time"]
        defaults = {
            "processed_source_file": [product.asset.path.name] * count,
            "source_record_id": [lineage.source_record_ids[0]] * count,
            "source_provenance": [product.asset.model_dump_json()] * count,
        }
        for coordinate, fallback in defaults.items():
            if coordinate not in values.coords:
                values = values.assign_coords({coordinate: ("time", fallback)})
        arrays.append(values)
        source_times.extend(values.time.values.astype("datetime64[ns]").tolist())
    if len(set(source_times)) != len(source_times):
        raise ValueError(
            f"Duplicate cube variable {variable} observation time; choose an explicit source priority"
        )
    combined = xr.concat(arrays, dim="time").sortby("time") if len(arrays) > 1 else arrays[0]
    return first_product, combined, list(dict.fromkeys(source_record_ids))


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
    grouped: dict[str, list[tuple[IngestedProduct, xr.DataArray]]] = {}
    for product in products:
        for variable in product.lineage:
            grouped.setdefault(variable, []).append((product, product.dataset[variable]))
    for variable, entries in grouped.items():
        product, series, source_record_ids = _combined_variable(entries, variable)
        policy = policies.get(variable, ResamplingPolicy())
        aligned = align_gridded_variable(
            series,
            target_times=target_times,
            target_latitudes=grid.latitudes,
            target_longitudes=grid.longitudes,
            spatial_method=policy.spatial_method,
            temporal_tolerance_minutes=policy.temporal_tolerance_minutes,
            temporal_method=policy.temporal_method,
        )
        values = np.asarray(aligned.values)
        cube[variable] = (("time", "y", "x"), values)
        cube[variable].attrs.update(
            _variable_attrs(
                product,
                variable,
                grid,
                policy,
                source_record_ids=source_record_ids,
            )
        )
        mask_name = f"{variable}__missing"
        cube[mask_name] = (("time", "y", "x"), ~np.isfinite(values))
        cube[mask_name].attrs.update(
            {
                "variable_status": "DERIVED",
                "meaning": f"True where {variable} is unavailable after explicit alignment",
                "source_variable": variable,
            }
        )
        cube[f"{variable}__observation_time"] = (
            "time",
            aligned.source_observation_time.values.astype("datetime64[ns]"),
        )
        cube[f"{variable}__age_minutes"] = (
            "time",
            np.asarray(aligned.source_age_minutes.values, dtype=float),
        )
        cube[f"{variable}__available"] = (
            "time",
            np.asarray(aligned.source_available.values, dtype=bool),
        )
        for suffix, coordinate in (
            ("source_file", "processed_source_file"),
            ("source_record_id", "source_record_id"),
            ("provenance", "source_provenance"),
        ):
            raw = aligned.coords.get(coordinate)
            metadata = [""] * len(target_times) if raw is None else [
                _metadata_value(value) for value in raw.values
            ]
            cube[f"{variable}__{suffix}"] = ("time", metadata)
        for suffix in (
            "observation_time",
            "age_minutes",
            "available",
            "source_file",
            "source_record_id",
            "provenance",
        ):
            cube[f"{variable}__{suffix}"].attrs.update(
                {
                    "metadata_role": "alignment_metadata",
                    "source_variable": variable,
                }
            )
    return cube
