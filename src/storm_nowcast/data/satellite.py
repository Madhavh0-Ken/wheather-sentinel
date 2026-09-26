from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import xarray as xr
from pyproj import CRS, Transformer

from storm_nowcast.config import Bounds
from storm_nowcast.data.manual import IngestedProduct, _asset, _confirm_origin, load_cf_grid_product
from storm_nowcast.data.sources import MosdacSatelliteSource
from storm_nowcast.models.sensors import (
    SourceDescriptor,
    SpatialResolution,
    TemporalSupport,
    VariableLineage,
)


MOSDAC_DESCRIPTOR = SourceDescriptor(
    provider="ISRO MOSDAC",
    product="User-selected official INSAT product",
    sensor="SATELLITE",
    official_url="https://mosdac.gov.in/",
    access_method="authenticated manual import",
    authentication_required=True,
)

INSAT3DR_L1C_ASIA_MER_DESCRIPTOR = SourceDescriptor(
    provider="ISRO/SAC MOSDAC",
    product="3RIMG_L1C_ASIA_MER",
    sensor="SATELLITE",
    official_url="https://mosdac.gov.in/doi/164/",
    access_method="registered MOSDAC user order; authenticated manual import",
    authentication_required=True,
)


def _attr_value(attributes: h5py.AttributeManager, name: str) -> object:
    if name not in attributes:
        raise ValueError(f"Required INSAT-3DR L1C metadata attribute is missing: {name}")
    value = attributes[name]
    if isinstance(value, np.ndarray) and value.size == 1:
        value = value.reshape(-1)[0]
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8").strip()
    if isinstance(value, str):
        return value.strip()
    return value.item() if isinstance(value, np.generic) else value


def _parse_insat_time(value: object, *, field: str) -> datetime:
    text = str(value).strip().removesuffix("Z")
    for pattern in ("%d-%m-%YT%H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid {field} in INSAT-3DR L1C metadata: {value!r}")


def _projection_coordinates(handle: h5py.File) -> tuple[np.ndarray, np.ndarray, str]:
    required = ("X", "Y", "Projection_Information")
    missing = [name for name in required if name not in handle]
    if missing:
        raise ValueError(f"Required INSAT-3DR L1C projection datasets are missing: {', '.join(missing)}")
    projection = handle["Projection_Information"]
    mapping_name = str(_attr_value(projection.attrs, "grid_mapping_name")).lower()
    if mapping_name != "mercator":
        raise ValueError(f"3RIMG_L1C_ASIA_MER requires Mercator projection metadata, got {mapping_name!r}")
    cf_mapping = {
        "grid_mapping_name": mapping_name,
        "false_easting": float(_attr_value(projection.attrs, "false_easting")),
        "false_northing": float(_attr_value(projection.attrs, "false_northing")),
        "longitude_of_projection_origin": float(
            _attr_value(projection.attrs, "longitude_of_projection_origin")
        ),
        "standard_parallel": float(_attr_value(projection.attrs, "standard_parallel")),
        "semi_major_axis": float(_attr_value(projection.attrs, "semi_major_axis")),
        "semi_minor_axis": float(_attr_value(projection.attrs, "semi_minor_axis")),
    }
    try:
        native_crs = CRS.from_cf(cf_mapping)
        transformer = Transformer.from_crs(native_crs, CRS.from_epsg(4326), always_xy=True)
        x = np.asarray(handle["X"][:], dtype=float).squeeze()
        y = np.asarray(handle["Y"][:], dtype=float).squeeze()
        if x.ndim != 1 or y.ndim != 1:
            raise ValueError("INSAT-3DR L1C X and Y projection coordinates must be one-dimensional")
        xx, yy = np.meshgrid(x, y)
        longitude_2d, latitude_2d = transformer.transform(xx, yy)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid INSAT-3DR L1C Mercator projection metadata: {exc}") from exc
    if not (
        np.allclose(longitude_2d, longitude_2d[0:1, :], atol=1e-7, equal_nan=True)
        and np.allclose(latitude_2d, latitude_2d[:, 0:1], atol=1e-7, equal_nan=True)
    ):
        raise ValueError("INSAT-3DR L1C Mercator grid is not rectilinear after WGS84 transformation")
    return longitude_2d[0, :], latitude_2d[:, 0], native_crs.to_string()


def _decode_temperature_channel(
    handle: h5py.File,
    *,
    channel_name: str,
    lut_name: str,
) -> tuple[np.ndarray, SpatialResolution]:
    missing = [name for name in (channel_name, lut_name) if name not in handle]
    if missing:
        raise ValueError(f"Required INSAT-3DR L1C datasets are missing: {', '.join(missing)}")
    channel = handle[channel_name]
    counts = np.asarray(channel[:])
    if counts.ndim == 3 and counts.shape[0] == 1:
        counts = counts[0]
    if counts.ndim != 2:
        raise ValueError(f"{channel_name} must contain one two-dimensional observation")
    fill_value = int(_attr_value(channel.attrs, "_FillValue"))
    valid = counts != fill_value
    lut = np.asarray(handle[lut_name][:], dtype=float).squeeze()
    if lut.ndim != 1:
        raise ValueError(f"{lut_name} must be a one-dimensional lookup table")
    if np.any(counts[valid] >= lut.size):
        raise ValueError(f"{channel_name} contains a count outside {lut_name} lookup table")
    values = np.full(counts.shape, np.nan, dtype=float)
    values[valid] = lut[counts[valid].astype(np.int64)]
    lut_fill = float(_attr_value(handle[lut_name].attrs, "_FillValue"))
    values[np.isclose(values, lut_fill)] = np.nan
    units = str(_attr_value(handle[lut_name].attrs, "units"))
    if units != "K":
        raise ValueError(f"{lut_name} must declare kelvin units, got {units!r}")
    resolution_unit = str(_attr_value(channel.attrs, "resolution_unit")).lower()
    if resolution_unit != "km":
        raise ValueError(f"{channel_name} resolution must be expressed in km")
    resolution = SpatialResolution(
        grid_spacing_km=float(_attr_value(channel.attrs, "resolution")),
        native_description=f"{channel_name} native L1C channel grid",
        crs="MOSDAC file-supplied Mercator",
    )
    return values, resolution


def load_insat3dr_l1c_asia_mer(
    path: Path,
    *,
    bounds: Bounds,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> IngestedProduct:
    """Decode the documented MOSDAC INSAT-3DR L1C Asian-sector HDF product."""
    path = Path(path)
    _confirm_origin(is_synthetic=is_synthetic, confirmed_official_origin=confirmed_official_origin)
    try:
        handle_context = h5py.File(path, "r")
    except Exception as exc:
        raise ValueError(f"Unsupported or unreadable INSAT-3DR L1C HDF asset: {path.name}: {exc}") from exc
    with handle_context as handle:
        processing_level = str(_attr_value(handle.attrs, "Processing_Level")).upper()
        if processing_level != "L1C":
            raise ValueError(f"3RIMG_L1C_ASIA_MER requires Processing_Level L1C, got {processing_level!r}")
        sensor_id = str(_attr_value(handle.attrs, "Sensor_Id")).upper()
        sensor_name = str(_attr_value(handle.attrs, "Sensor_Name")).upper()
        if sensor_id != "IMG" or sensor_name != "IMAGER":
            raise ValueError("3RIMG_L1C_ASIA_MER requires the INSAT Imager sensor")
        satellite_name = str(_attr_value(handle.attrs, "Satellite_Name")).upper()
        if satellite_name != "INSAT-3DR":
            raise ValueError(f"Expected INSAT-3DR satellite metadata, got {satellite_name!r}")
        title = str(_attr_value(handle.attrs, "title")).upper()
        if "L1C" not in title or "ASIA_MER" not in title:
            raise ValueError("HDF title does not identify the L1C ASIA_MER product")
        acquisition_date = str(_attr_value(handle.attrs, "Acquisition_Date"))
        acquisition_clock = str(_attr_value(handle.attrs, "Acquisition_Time_in_GMT")).zfill(4)
        try:
            observation_time = datetime.strptime(
                f"{acquisition_date} {acquisition_clock}", "%d%b%Y %H%M"
            ).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("Invalid Acquisition_Date/Acquisition_Time_in_GMT in INSAT-3DR L1C metadata") from exc
        observation_start = _parse_insat_time(
            _attr_value(handle.attrs, "Acquisition_Start_Time"), field="Acquisition_Start_Time"
        )
        observation_end = _parse_insat_time(
            _attr_value(handle.attrs, "Acquisition_End_Time"), field="Acquisition_End_Time"
        )
        longitude, latitude, native_crs = _projection_coordinates(handle)
        tir1, tir1_resolution = _decode_temperature_channel(
            handle, channel_name="IMG_TIR1", lut_name="IMG_TIR1_TEMP"
        )
        if tir1.shape != (latitude.size, longitude.size):
            raise ValueError("IMG_TIR1 dimensions do not match the file-supplied X/Y projection grid")
        decoded: list[tuple[str, str, str, np.ndarray, SpatialResolution]] = [
            (
                "infrared_brightness_temperature",
                "IMG_TIR1",
                "IMG_TIR1_TEMP",
                tir1,
                tir1_resolution,
            )
        ]
        if "IMG_WV" in handle or "IMG_WV_TEMP" in handle:
            water_vapour, water_vapour_resolution = _decode_temperature_channel(
                handle, channel_name="IMG_WV", lut_name="IMG_WV_TEMP"
            )
            if water_vapour.shape != tir1.shape:
                raise ValueError("IMG_WV dimensions do not match the file-supplied X/Y projection grid")
            decoded.append(
                (
                    "water_vapour_brightness_temperature",
                    "IMG_WV",
                    "IMG_WV_TEMP",
                    water_vapour,
                    water_vapour_resolution,
                )
            )
        product_creation_time = str(_attr_value(handle.attrs, "Product_Creation_Time"))

    asset = _asset(path, INSAT3DR_L1C_ASIA_MER_DESCRIPTOR, is_synthetic=is_synthetic)
    dataset = xr.Dataset(
        coords={
            "time": [np.datetime64(observation_time.replace(tzinfo=None), "ns")],
            "latitude": latitude,
            "longitude": longitude,
        }
    )
    lineage: dict[str, VariableLineage] = {}
    for canonical, channel_name, lut_name, values, resolution in decoded:
        dataset[canonical] = (("time", "latitude", "longitude"), values[np.newaxis, ...])
        dataset[canonical].attrs.update(
            {
                "units": "K",
                "provider": INSAT3DR_L1C_ASIA_MER_DESCRIPTOR.provider,
                "product": INSAT3DR_L1C_ASIA_MER_DESCRIPTOR.product,
                "source_variable": channel_name,
                "calibration_lookup_table": lut_name,
                "variable_status": "OBSERVED",
                "native_resolution": resolution.model_dump_json(),
            }
        )
        lineage[canonical] = VariableLineage(
            variable=canonical,
            source_record_ids=[f"sha256:{asset.sha256}"],
            status="OBSERVED",
            native_units="digital count",
            processed_units="K",
            native_spatial_resolution=resolution,
            native_temporal_resolution_minutes=30.0,
            processing_steps=[
                f"decoded {channel_name} digital counts from user-supplied official HDF",
                f"applied file-supplied {lut_name} brightness-temperature lookup table",
                "transformed file-supplied Mercator coordinates to EPSG:4326",
                "subset to configured bounds",
            ],
        )
    dataset = dataset.sortby("latitude").sortby("longitude")
    dataset = dataset.sel(
        latitude=slice(bounds.min_lat, bounds.max_lat),
        longitude=slice(bounds.min_lon, bounds.max_lon),
    )
    if dataset.sizes.get("latitude", 0) == 0 or dataset.sizes.get("longitude", 0) == 0:
        raise ValueError("The official INSAT-3DR asset does not intersect the configured study area")
    dataset.attrs.update(
        {
            "provider": INSAT3DR_L1C_ASIA_MER_DESCRIPTOR.provider,
            "product": INSAT3DR_L1C_ASIA_MER_DESCRIPTOR.product,
            "source_sha256": asset.sha256,
            "is_synthetic": int(is_synthetic),
            "crs": "EPSG:4326",
            "native_crs": native_crs,
            "product_creation_time": product_creation_time,
            "format_contract": "MOSDAC INSAT-3D Data Products Format Document v1.1",
            "verification_status": "documented schema; authorized real-file verification pending",
        }
    )
    return IngestedProduct(
        dataset=dataset,
        asset=asset,
        lineage=lineage,
        temporal_support=TemporalSupport(
            observation_start=observation_start,
            observation_end=observation_end,
            native_resolution_minutes=30.0,
            availability_time=_parse_insat_time(product_creation_time, field="Product_Creation_Time"),
        ),
    )


def load_mosdac_file(
    path: Path,
    *,
    bounds: Bounds,
    variable_map: dict[str, str],
    native_resolution: SpatialResolution,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> IngestedProduct:
    return load_cf_grid_product(
        path,
        source=MOSDAC_DESCRIPTOR,
        bounds=bounds,
        variable_map=variable_map,
        native_resolution=native_resolution,
        is_synthetic=is_synthetic,
        confirmed_official_origin=confirmed_official_origin,
    )


def derive_satellite_evolution(
    previous: IngestedProduct,
    current: IngestedProduct,
    *,
    variable: str = "infrared_brightness_temperature",
    cold_threshold_k: float = 235.0,
) -> xr.Dataset:
    if variable not in previous.dataset or variable not in current.dataset:
        raise ValueError(f"Both products must contain {variable}")
    first = previous.dataset[variable]
    second = current.dataset[variable]
    if str(first.attrs.get("units")) != "K" or str(second.attrs.get("units")) != "K":
        raise ValueError("Cloud-top cooling requires brightness temperature observations in kelvin")
    first_time = np.asarray(previous.dataset.time.values).astype("datetime64[ns]").max()
    second_time = np.asarray(current.dataset.time.values).astype("datetime64[ns]").max()
    elapsed_hours = float((second_time - first_time) / np.timedelta64(1, "h"))
    if elapsed_hours <= 0:
        raise ValueError("Satellite observations must advance in time")
    aligned_first, aligned_second = xr.align(first.squeeze(drop=True), second.squeeze(drop=True), join="exact")
    cooling = (aligned_first - aligned_second) / elapsed_hours
    cooling.name = "cloud_top_cooling_rate_k_per_hour"
    cooling.attrs.update(
        {
            "units": "K h-1",
            "variable_status": "DERIVED",
            "derivation": "(previous brightness temperature - current brightness temperature) / elapsed hours",
        }
    )
    valid = np.isfinite(aligned_first) & np.isfinite(aligned_second)
    valid_count = int(valid.sum())
    previous_cold = int(((aligned_first <= cold_threshold_k) & valid).sum())
    current_cold = int(((aligned_second <= cold_threshold_k) & valid).sum())
    expansion = (current_cold - previous_cold) / valid_count / elapsed_hours if valid_count else np.nan
    result = cooling.to_dataset()
    result.attrs.update(
        {
            "variable_status": "DERIVED",
            "cold_threshold_k": cold_threshold_k,
            "cold_cloud_expansion_fraction_per_hour": float(expansion),
            "source_record_ids": [previous.asset.sha256, current.asset.sha256],
        }
    )
    return result

__all__ = [
    "MosdacSatelliteSource",
    "load_mosdac_file",
    "load_insat3dr_l1c_asia_mer",
    "derive_satellite_evolution",
]
