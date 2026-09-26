from __future__ import annotations

from datetime import timedelta

from pyproj import Geod

from storm_nowcast.models.schemas import ForecastPoint, StormCell


WGS84 = Geod(ellps="WGS84")


def forecast_track(
    cell: StormCell,
    leads: tuple[int, ...] = (30, 60, 120),
    *,
    base_uncertainty_km: float = 12.0,
    uncertainty_growth_km_per_hour: float = 18.0,
) -> list[ForecastPoint]:
    stationary = cell.speed_kmh < 1.0 or cell.bearing_deg is None
    results: list[ForecastPoint] = []
    for lead in leads:
        hours = lead / 60
        distance_km = 0.0 if stationary else cell.speed_kmh * hours
        if distance_km:
            longitude, latitude, _ = WGS84.fwd(
                cell.current.centroid_lon,
                cell.current.centroid_lat,
                cell.bearing_deg,
                distance_km * 1000,
            )
        else:
            latitude = cell.current.centroid_lat
            longitude = cell.current.centroid_lon
        uncertainty = base_uncertainty_km + uncertainty_growth_km_per_hour * hours
        if stationary:
            confidence = "LOW"
        elif lead <= 30 and len(cell.history) >= 3:
            confidence = "HIGH"
        elif lead <= 60:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        results.append(
            ForecastPoint(
                lead_minutes=lead,
                valid_at=cell.last_seen + timedelta(minutes=lead),
                latitude=latitude,
                longitude=longitude,
                uncertainty_km=uncertainty,
                confidence=confidence,
            )
        )
    return results
