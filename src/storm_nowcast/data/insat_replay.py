from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.data.manual import IngestedProduct
from storm_nowcast.data.satellite import _parse_insat_time
from storm_nowcast.fusion.cube import ResamplingPolicy, TargetGridSpec, build_weather_cube
from storm_nowcast.models.sensors import (
    RawAsset,
    SpatialResolution,
    TemporalSupport,
    VariableLineage,
)


INSAT_PROVIDER = "ISRO/SAC MOSDAC"
INSAT_PRODUCT = "3RIMG_L1C_ASIA_MER"
INSAT_VARIABLES = {
    "infrared_brightness_temperature": ("IMG_TIR1", "IMG_TIR1_TEMP"),
    "water_vapour_brightness_temperature": ("IMG_WV", "IMG_WV_TEMP"),
}


def _require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _observation_time(dataset: xr.Dataset, path: Path) -> datetime:
    if "time" not in dataset.coords or dataset.sizes.get("time") != 1:
        raise ValueError(f"Processed INSAT file must contain exactly one observation time: {path.name}")
    value = dataset.time.values[0].astype("datetime64[ns]")
    if np.isnat(value):
        raise ValueError(f"Processed INSAT observation time is invalid: {path.name}")
    nanoseconds = value.astype(np.int64)
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)


def _read_dataset(path: Path) -> xr.Dataset:
    try:
        with xr.open_dataset(path, engine="h5netcdf") as opened:
            return opened.load()
    except Exception as exc:
        raise ValueError(f"Unsupported processed INSAT NetCDF: {path.name}: {exc}") from exc


def _validate_processed_dataset(dataset: xr.Dataset, path: Path) -> None:
    if dataset.attrs.get("provider") != INSAT_PROVIDER:
        raise ValueError(f"Invalid processed INSAT provider in {path.name}")
    if dataset.attrs.get("product") != INSAT_PRODUCT:
        raise ValueError(f"Invalid processed INSAT product in {path.name}")
    if bool(dataset.attrs.get("is_synthetic", False)) not in {True, False}:
        raise ValueError(f"Invalid processed INSAT synthetic flag in {path.name}")
    required_coords = {"time", "latitude", "longitude"}
    if not required_coords.issubset(dataset.coords):
        raise ValueError(f"Processed INSAT coordinates are incomplete in {path.name}")
    if set(dataset.data_vars) != set(INSAT_VARIABLES):
        raise ValueError(
            f"Processed INSAT variables are incomplete or unsupported in {path.name}: "
            f"expected {sorted(INSAT_VARIABLES)}, got {sorted(dataset.data_vars)}"
        )
    if dataset.attrs.get("crs") != "EPSG:4326":
        raise ValueError(f"Processed INSAT analysis CRS must be EPSG:4326 in {path.name}")
    if "Mercator" not in str(dataset.attrs.get("native_crs", "")):
        raise ValueError(f"Processed INSAT native CRS must identify Mercator in {path.name}")
    if dataset.attrs.get("format_contract") != (
        "MOSDAC INSAT-3D Data Products Format Document v1.1"
    ):
        raise ValueError(f"Invalid processed INSAT format contract in {path.name}")
    for variable in dataset.data_vars:
        values = dataset[variable]
        source_variable, lookup = INSAT_VARIABLES[variable]
        if values.dims != ("time", "latitude", "longitude"):
            raise ValueError(f"Invalid processed INSAT dimensions for {variable} in {path.name}")
        expected = {
            "units": "K",
            "provider": INSAT_PROVIDER,
            "product": INSAT_PRODUCT,
            "source_variable": source_variable,
            "calibration_lookup_table": lookup,
            "variable_status": "OBSERVED",
        }
        for key, expected_value in expected.items():
            if values.attrs.get(key) != expected_value:
                raise ValueError(f"Invalid processed INSAT {key} for {variable} in {path.name}")


def _validate_processed_provenance(
    dataset: xr.Dataset,
    path: Path,
    *,
    asset: RawAsset,
    lineage: dict[str, VariableLineage],
    temporal_support: TemporalSupport,
) -> None:
    observation_time = _observation_time(dataset, path)
    start_offset = (temporal_support.observation_start - observation_time).total_seconds()
    if not 0 <= start_offset < 60:
        raise ValueError(f"Processed INSAT observation time conflicts with provenance for {path.name}")
    observation_duration = (
        temporal_support.observation_end - temporal_support.observation_start
    ).total_seconds()
    if not 0 <= observation_duration <= 30 * 60:
        raise ValueError(f"Processed INSAT observation window conflicts for {path.name}")
    if temporal_support.native_resolution_minutes != 30.0:
        raise ValueError(f"Processed INSAT temporal resolution conflicts for {path.name}")
    if temporal_support.availability_time is None:
        raise ValueError(f"Processed INSAT availability time is missing for {path.name}")
    try:
        product_creation_time = _parse_insat_time(
            dataset.attrs["product_creation_time"],
            field="Product_Creation_Time",
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid processed INSAT product creation time in {path.name}") from exc
    if temporal_support.availability_time != product_creation_time:
        raise ValueError(f"Processed INSAT availability time conflicts for {path.name}")
    if temporal_support.availability_time < temporal_support.observation_end:
        raise ValueError(f"Processed INSAT availability time precedes observation end in {path.name}")
    if asset.acquired_at is None or asset.acquired_at < temporal_support.availability_time:
        raise ValueError(f"Processed INSAT acquisition time conflicts for {path.name}")

    expected_record_id = f"sha256:{asset.sha256}"
    for variable, (source_variable, _lookup) in INSAT_VARIABLES.items():
        item = lineage[variable]
        if item.status != "OBSERVED":
            raise ValueError(f"Processed INSAT lineage status conflicts for {variable} in {path.name}")
        if item.native_units != "digital count" or item.processed_units != "K":
            raise ValueError(f"Processed INSAT lineage units conflict for {variable} in {path.name}")
        if item.native_temporal_resolution_minutes != 30.0:
            raise ValueError(
                f"Processed INSAT lineage temporal resolution conflicts for {variable} in {path.name}"
            )
        if item.resampling_method != "none" or item.analysis_grid_resolution_km is not None:
            raise ValueError(f"Processed INSAT lineage resampling conflicts for {variable} in {path.name}")
        if item.source_record_ids != [expected_record_id]:
            raise ValueError(f"Processed INSAT source record conflicts for {variable} in {path.name}")
        try:
            dataset_resolution = SpatialResolution.model_validate_json(
                dataset[variable].attrs["native_resolution"]
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"Invalid processed INSAT native spatial metadata for {variable} in {path.name}"
            ) from exc
        if (
            item.native_spatial_resolution != dataset_resolution
            or item.native_spatial_resolution.crs != "MOSDAC file-supplied Mercator"
            or item.native_spatial_resolution.native_description
            != f"{source_variable} native L1C channel grid"
        ):
            raise ValueError(
                f"Processed INSAT native spatial metadata conflicts for {variable} in {path.name}"
            )
    if lineage["infrared_brightness_temperature"].native_spatial_resolution.grid_spacing_km != 4.0:
        raise ValueError(f"Processed INSAT TIR1 native spatial metadata conflicts in {path.name}")


def _load_product(path: Path, dataset: xr.Dataset) -> IngestedProduct:
    provenance_path = path.with_suffix(path.suffix + ".provenance.json")
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        asset = RawAsset.model_validate(payload["asset"])
        lineage = {
            name: VariableLineage.model_validate(value)
            for name, value in payload["lineage"].items()
        }
        temporal_support = TemporalSupport.model_validate(payload["temporal_support"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid processed INSAT provenance for {path.name}: {exc}") from exc

    if asset.source.provider != dataset.attrs.get("provider"):
        raise ValueError(f"Processed INSAT provider conflicts with provenance for {path.name}")
    if asset.source.product != dataset.attrs.get("product") or asset.source.sensor != "SATELLITE":
        raise ValueError(f"Processed INSAT product conflicts with provenance for {path.name}")
    if asset.sha256 != dataset.attrs.get("source_sha256"):
        raise ValueError(f"Processed INSAT source checksum conflicts with provenance for {path.name}")
    if asset.is_synthetic != bool(dataset.attrs.get("is_synthetic", False)):
        raise ValueError(f"Processed INSAT synthetic status conflicts with provenance for {path.name}")
    if set(lineage) != set(dataset.data_vars):
        raise ValueError(f"Processed INSAT variables conflict with provenance for {path.name}")
    for variable, item in lineage.items():
        if item.variable != variable or item.processed_units != "K":
            raise ValueError(f"Processed INSAT lineage conflicts for {variable} in {path.name}")
        if f"sha256:{asset.sha256}" not in item.source_record_ids:
            raise ValueError(f"Processed INSAT source record conflicts for {variable} in {path.name}")

    _validate_processed_provenance(
        dataset,
        path,
        asset=asset,
        lineage=lineage,
        temporal_support=temporal_support,
    )

    source_record_id = lineage["infrared_brightness_temperature"].source_record_ids[0]
    enriched = dataset.assign_coords(
        processed_source_file=("time", [path.name]),
        source_record_id=("time", [source_record_id]),
        source_provenance=("time", [json.dumps(payload, sort_keys=True)]),
    )
    return IngestedProduct(
        dataset=enriched,
        asset=asset,
        lineage=lineage,
        temporal_support=temporal_support,
    )


def load_processed_insat_observations(
    directory: Path,
    *,
    event_start: datetime,
    event_end: datetime,
    max_age_minutes: int = 30,
) -> list[IngestedProduct]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    start = _require_utc(event_start, "event_start")
    end = _require_utc(event_end, "event_end")
    if end < start:
        raise ValueError("event_end must not precede event_start")
    if max_age_minutes < 0:
        raise ValueError("max_age_minutes must be non-negative")
    earliest = start - timedelta(minutes=max_age_minutes)

    products: list[IngestedProduct] = []
    seen: set[datetime] = set()
    for path in sorted(directory.glob("*.nc")):
        dataset = _read_dataset(path)
        observation_time = _observation_time(dataset, path)
        if observation_time < earliest or observation_time > end:
            continue
        _validate_processed_dataset(dataset, path)
        if observation_time in seen:
            raise ValueError(f"Duplicate INSAT observation time: {observation_time.isoformat()}")
        seen.add(observation_time)
        products.append(_load_product(path, dataset))
    return products


def insat_directory_revision(directory: Path | None) -> tuple[tuple[str, int, int], ...]:
    if directory is None or not Path(directory).is_dir():
        return ()
    revision: list[tuple[str, int, int]] = []
    for path in sorted(Path(directory).glob("*.nc*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        revision.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(revision)


def build_insat_replay_cube(
    directory: Path,
    *,
    target_times: tuple[np.datetime64, ...],
    event_start: datetime,
    event_end: datetime,
    max_age_minutes: int = 30,
) -> xr.Dataset | None:
    products = load_processed_insat_observations(
        directory,
        event_start=event_start,
        event_end=event_end,
        max_age_minutes=max_age_minutes,
    )
    if not products:
        return None
    first = products[0]
    latitudes = np.asarray(first.dataset.latitude.values, dtype=float)
    longitudes = np.asarray(first.dataset.longitude.values, dtype=float)
    for product in products[1:]:
        if not (
            np.array_equal(product.dataset.latitude.values, latitudes)
            and np.array_equal(product.dataset.longitude.values, longitudes)
        ):
            raise ValueError("Processed INSAT source grids must match within one replay event")
    native_resolution = first.lineage[
        "infrared_brightness_temperature"
    ].native_spatial_resolution.grid_spacing_km
    if native_resolution is None:
        raise ValueError("Processed INSAT TIR1 native grid spacing is missing")
    policies = {
        variable: ResamplingPolicy(
            spatial_method="nearest",
            temporal_tolerance_minutes=max_age_minutes,
            temporal_method="backward",
        )
        for variable in first.lineage
    }
    cube = build_weather_cube(
        products,
        grid=TargetGridSpec(
            latitudes=tuple(float(value) for value in latitudes),
            longitudes=tuple(float(value) for value in longitudes),
            resolution_km=native_resolution,
        ),
        target_times=target_times,
        policies=policies,
    )
    cube.attrs.update(
        {
            "provider": INSAT_PROVIDER,
            "product": INSAT_PRODUCT,
            "max_age_minutes": max_age_minutes,
            "spatial_alignment": "native source grid; no artificial upscaling",
        }
    )
    return cube


__all__ = [
    "build_insat_replay_cube",
    "insat_directory_revision",
    "load_processed_insat_observations",
]
