from pathlib import Path

from storm_nowcast.config import Bounds
from storm_nowcast.data.manual import IngestedProduct, load_cf_grid_product
from storm_nowcast.models.sensors import SourceDescriptor, SpatialResolution


def load_official_nwp_file(
    path: Path,
    *,
    source: SourceDescriptor,
    bounds: Bounds,
    variable_map: dict[str, str],
    native_resolution: SpatialResolution,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> IngestedProduct:
    if source.sensor != "NWP":
        raise ValueError("NWP loader requires a SourceDescriptor with sensor='NWP'")
    return load_cf_grid_product(
        path,
        source=source,
        bounds=bounds,
        variable_map=variable_map,
        native_resolution=native_resolution,
        is_synthetic=is_synthetic,
        confirmed_official_origin=confirmed_official_origin,
    )
