from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.data.manual import IngestedProduct
from storm_nowcast.fusion.cube import ResamplingPolicy, TargetGridSpec, build_weather_cube
from storm_nowcast.models.sensors import RawAsset, TemporalSupport, VariableLineage


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
    if "infrared_brightness_temperature" not in dataset.data_vars:
        raise ValueError(f"Processed INSAT TIR1 brightness temperature is missing in {path.name}")
    unsupported = set(dataset.data_vars) - set(INSAT_VARIABLES)
    if unsupported:
        raise ValueError(f"Unsupported processed INSAT variables in {path.name}: {sorted(unsupported)}")
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


__all__ = ["build_insat_replay_cube", "load_processed_insat_observations"]
