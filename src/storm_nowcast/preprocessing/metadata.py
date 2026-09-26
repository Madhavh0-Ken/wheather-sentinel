from __future__ import annotations

import json

import xarray as xr


def validate_resolution_claims(dataset: xr.Dataset) -> xr.Dataset:
    """Reject fused variables that hide native resolution or imply false precision."""
    for name, variable in dataset.data_vars.items():
        if name.endswith("__missing"):
            continue
        required = {
            "native_spatial_resolution_km",
            "analysis_grid_resolution_km",
            "resampling_method",
            "variable_status",
            "source_record_ids",
        }
        missing = sorted(key for key in required if key not in variable.attrs)
        if missing:
            raise ValueError(f"{name} is missing required resolution/provenance attributes: {', '.join(missing)}")
        source_ids = json.loads(variable.attrs["source_record_ids"])
        if not source_ids:
            raise ValueError(f"{name} must retain at least one source record ID")
        native = variable.attrs["native_spatial_resolution_km"]
        analysis = variable.attrs["analysis_grid_resolution_km"]
        if native is not None and analysis < native and not variable.attrs.get("physical_resolution_warning"):
            raise ValueError(f"{name} is resampled finer than native data without a physical-resolution warning")
    return dataset
