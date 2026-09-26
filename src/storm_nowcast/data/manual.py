from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.models.sensors import (
    RawAsset,
    SourceDescriptor,
    SpatialResolution,
    TemporalSupport,
    VariableLineage,
)


@dataclass(frozen=True)
class IngestedProduct:
    dataset: xr.Dataset
    asset: RawAsset
    lineage: dict[str, VariableLineage]
    temporal_support: TemporalSupport


@dataclass(frozen=True)
class PointObservationProduct:
    frame: pd.DataFrame
    asset: RawAsset
    units: dict[str, str]


def discover_manual_files(directory: Path, extensions: tuple[str, ...]) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    allowed = {suffix.lower() for suffix in extensions}
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in allowed)


def _confirm_origin(*, is_synthetic: bool, confirmed_official_origin: bool) -> None:
    if not is_synthetic and not confirmed_official_origin:
        raise ValueError(
            "Manual production files require confirmed_official_origin=True; "
            "StormNowcast cannot infer official origin from a filename."
        )


def _asset(path: Path, source: SourceDescriptor, *, is_synthetic: bool) -> RawAsset:
    return RawAsset(
        path=path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        source=source,
        acquired_at=datetime.now(timezone.utc),
        is_synthetic=is_synthetic,
    )


def _coordinate_name(dataset: xr.Dataset, standard_name: str, aliases: tuple[str, ...]) -> str:
    for name in dataset.coords:
        if str(dataset[name].attrs.get("standard_name", "")).lower() == standard_name:
            return name
    for alias in aliases:
        if alias in dataset.coords:
            return alias
    raise ValueError(f"CF-compatible {standard_name} coordinate was not found")


def load_cf_grid_product(
    path: Path,
    *,
    source: SourceDescriptor,
    bounds: Bounds,
    variable_map: dict[str, str],
    native_resolution: SpatialResolution,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> IngestedProduct:
    """Load explicitly mapped variables from a CF-like NetCDF/HDF5 asset.

    This deliberately does not infer channel semantics from names.
    """
    if not variable_map:
        raise ValueError("An explicit variable_map is required; channel semantics are never guessed")
    path = Path(path)
    _confirm_origin(is_synthetic=is_synthetic, confirmed_official_origin=confirmed_official_origin)
    try:
        opened = xr.open_dataset(path, engine="h5netcdf")
    except Exception as exc:
        raise ValueError(f"Unsupported or unreadable NetCDF/HDF5 asset: {path.name}: {exc}") from exc
    with opened:
        dataset = opened.load()
    latitude_name = _coordinate_name(dataset, "latitude", ("latitude", "lat"))
    longitude_name = _coordinate_name(dataset, "longitude", ("longitude", "lon"))
    rename: dict[str, str] = {}
    if latitude_name != "latitude":
        rename[latitude_name] = "latitude"
    if longitude_name != "longitude":
        rename[longitude_name] = "longitude"
    dataset = dataset.rename(rename).sortby("latitude").sortby("longitude")
    if "time" not in dataset.coords:
        raw_time = dataset.attrs.get("time_coverage_start") or dataset.attrs.get("observation_time")
        if raw_time is None:
            raise ValueError("A time coordinate or time_coverage_start metadata value is required")
        dataset = dataset.expand_dims(time=[np.datetime64(str(raw_time).replace("Z", ""))])
    missing = [source_name for source_name in variable_map.values() if source_name not in dataset.data_vars]
    if missing:
        raise ValueError(f"Mapped source variables are absent: {', '.join(missing)}")
    output = xr.Dataset(coords={name: dataset.coords[name] for name in dataset.coords})
    asset = _asset(path, source, is_synthetic=is_synthetic)
    lineage: dict[str, VariableLineage] = {}
    for canonical, source_name in variable_map.items():
        values = dataset[source_name].where(np.isfinite(dataset[source_name]))
        units = str(values.attrs.get("units", "")).strip()
        if not units:
            raise ValueError(f"Variable {source_name} has no units metadata")
        values.attrs.update(
            {
                "source_variable": source_name,
                "provider": source.provider,
                "product": source.product,
                "variable_status": "OBSERVED",
                "native_resolution": native_resolution.model_dump_json(),
            }
        )
        output[canonical] = values
        lineage[canonical] = VariableLineage(
            variable=canonical,
            source_record_ids=[f"sha256:{asset.sha256}"],
            status="OBSERVED",
            native_units=units,
            processed_units=units,
            native_spatial_resolution=native_resolution,
            resampling_method="none",
            processing_steps=["decoded from user-supplied official asset", "subset to configured bounds"],
        )
    output = output.sel(
        latitude=slice(bounds.min_lat, bounds.max_lat),
        longitude=slice(bounds.min_lon, bounds.max_lon),
    )
    if output.sizes.get("latitude", 0) == 0 or output.sizes.get("longitude", 0) == 0:
        raise ValueError("The official asset does not intersect the configured study area")
    times = pd.to_datetime(output.time.values, utc=True)
    temporal = TemporalSupport(
        observation_start=times.min().to_pydatetime(),
        observation_end=times.max().to_pydatetime(),
    )
    output.attrs.update(
        {
            "provider": source.provider,
            "product": source.product,
            "source_sha256": asset.sha256,
            "is_synthetic": is_synthetic,
            "crs": native_resolution.crs,
        }
    )
    return IngestedProduct(output, asset, lineage, temporal)


def load_explicit_point_csv(
    path: Path,
    *,
    source: SourceDescriptor,
    column_map: dict[str, str],
    bounds: Bounds,
    units: dict[str, str] | None = None,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> PointObservationProduct:
    required = {"timestamp", "latitude", "longitude"}
    if not required.issubset(column_map):
        raise ValueError("An explicit mapping for timestamp, latitude, and longitude is required")
    _confirm_origin(is_synthetic=is_synthetic, confirmed_official_origin=confirmed_official_origin)
    path = Path(path)
    frame = pd.read_csv(path)
    missing = [name for name in column_map.values() if name not in frame.columns]
    if missing:
        raise ValueError(f"Mapped CSV columns are absent: {', '.join(missing)}")
    inverse = {source_name: canonical for canonical, source_name in column_map.items()}
    frame = frame[list(inverse)].rename(columns=inverse)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="raise")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="raise")
    frame = frame.loc[
        frame.latitude.between(bounds.min_lat, bounds.max_lat)
        & frame.longitude.between(bounds.min_lon, bounds.max_lon)
    ].sort_values("timestamp", ignore_index=True)
    return PointObservationProduct(
        frame=frame,
        asset=_asset(path, source, is_synthetic=is_synthetic),
        units=dict(units or {}),
    )
