from pathlib import Path

from storm_nowcast.config import Bounds
from storm_nowcast.data.manual import PointObservationProduct, load_explicit_point_csv
from storm_nowcast.data.sources import ImdStationSource
from storm_nowcast.models.sensors import SourceDescriptor


IMD_STATION_DESCRIPTOR = SourceDescriptor(
    provider="India Meteorological Department",
    product="User-selected official AWS/ARG or station product",
    sensor="SURFACE",
    official_url="https://mausam.imd.gov.in/",
    access_method="official manual import",
    authentication_required=True,
)


def load_imd_station_file(
    path: Path,
    *,
    column_map: dict[str, str],
    units: dict[str, str],
    bounds: Bounds,
    is_synthetic: bool = False,
    confirmed_official_origin: bool = False,
) -> PointObservationProduct:
    unknown_units = set(units) - set(column_map)
    if unknown_units:
        raise ValueError(f"Units supplied for unmapped variables: {', '.join(sorted(unknown_units))}")
    return load_explicit_point_csv(
        path,
        source=IMD_STATION_DESCRIPTOR,
        column_map=column_map,
        units=units,
        bounds=bounds,
        is_synthetic=is_synthetic,
        confirmed_official_origin=confirmed_official_origin,
    )

__all__ = ["ImdStationSource", "load_imd_station_file"]
