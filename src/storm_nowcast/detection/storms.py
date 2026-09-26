from __future__ import annotations

from datetime import datetime

import numpy as np
import xarray as xr
from shapely.geometry import box, mapping
from shapely.ops import unary_union
from skimage.measure import label

from storm_nowcast.config import DetectionConfig
from storm_nowcast.models.schemas import DetectedCell
from storm_nowcast.preprocessing.grid import grid_cell_area_km2


def _spacing(values: np.ndarray, fallback: float = 0.07277) -> float:
    if len(values) < 2:
        return fallback
    return float(np.median(np.diff(values)))


def detect_cells(
    field: xr.DataArray,
    timestamp: datetime,
    config: DetectionConfig,
) -> list[DetectedCell]:
    if field.dims != ("latitude", "longitude"):
        raise ValueError("Detection field dimensions must be latitude, longitude")
    values = np.asarray(field.values, dtype=float)
    active = np.isfinite(values) & (values >= config.threshold_mm_hr)
    labels = label(active, connectivity=1)
    latitudes = np.asarray(field.latitude.values, dtype=float)
    longitudes = np.asarray(field.longitude.values, dtype=float)
    dlat = _spacing(latitudes)
    dlon = _spacing(longitudes)
    is_synthetic = bool(field.attrs.get("is_synthetic", False))
    cells: list[DetectedCell] = []

    for component_id in range(1, labels.max() + 1):
        rows, cols = np.where(labels == component_id)
        if len(rows) < config.minimum_pixels:
            continue
        intensities = values[rows, cols]
        weights = intensities / intensities.sum() if intensities.sum() > 0 else np.ones_like(intensities) / len(intensities)
        centroid_lat = float(np.sum(latitudes[rows] * weights))
        centroid_lon = float(np.sum(longitudes[cols] * weights))
        geometries = [
            box(
                longitudes[col] - dlon / 2,
                latitudes[row] - dlat / 2,
                longitudes[col] + dlon / 2,
                latitudes[row] + dlat / 2,
            )
            for row, col in zip(rows, cols, strict=True)
        ]
        footprint = unary_union(geometries)
        min_lon, min_lat, max_lon, max_lat = footprint.bounds
        area = sum(grid_cell_area_km2(float(latitudes[row]), dlat, dlon) for row in rows)
        cells.append(
            DetectedCell(
                local_id=len(cells) + 1,
                timestamp=timestamp,
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                area_km2=area,
                max_intensity=float(np.max(intensities)),
                mean_intensity=float(np.mean(intensities)),
                pixel_count=len(rows),
                bbox=(min_lat, min_lon, max_lat, max_lon),
                polygon_geojson=mapping(footprint),
                is_synthetic=is_synthetic,
            )
        )
    return cells
