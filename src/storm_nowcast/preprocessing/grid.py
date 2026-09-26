from __future__ import annotations

from pyproj import Geod


WGS84 = Geod(ellps="WGS84")


def grid_cell_area_km2(latitude: float, delta_lat: float, delta_lon: float) -> float:
    half_lat = abs(delta_lat) / 2
    half_lon = abs(delta_lon) / 2
    lons = [
        -half_lon,
        half_lon,
        half_lon,
        -half_lon,
        -half_lon,
    ]
    lats = [
        latitude - half_lat,
        latitude - half_lat,
        latitude + half_lat,
        latitude + half_lat,
        latitude - half_lat,
    ]
    area_m2, _ = WGS84.polygon_area_perimeter(lons, lats)
    return abs(area_m2) / 1_000_000

