from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.manual import IngestedProduct, load_cf_grid_product
from storm_nowcast.data.sources import MosdacSatelliteSource
from storm_nowcast.models.sensors import SourceDescriptor, SpatialResolution


MOSDAC_DESCRIPTOR = SourceDescriptor(
    provider="ISRO MOSDAC",
    product="User-selected official INSAT product",
    sensor="SATELLITE",
    official_url="https://mosdac.gov.in/",
    access_method="authenticated manual import",
    authentication_required=True,
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

__all__ = ["MosdacSatelliteSource", "load_mosdac_file", "derive_satellite_evolution"]
