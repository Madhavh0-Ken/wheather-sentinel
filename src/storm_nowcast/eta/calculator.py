from __future__ import annotations

from datetime import datetime

from storm_nowcast.models.schemas import ETAResult, ForecastPoint
from storm_nowcast.tracking.tracker import haversine_km


def calculate_eta(
    target_lat: float,
    target_lon: float,
    forecasts: list[ForecastPoint],
    issued_at: datetime,
) -> ETAResult:
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ValueError("Forecast issuance time must be timezone-aware")
    if not forecasts:
        raise ValueError("At least one forecast point is required")

    distances = [
        haversine_km(target_lat, target_lon, point.latitude, point.longitude)
        for point in forecasts
    ]
    closest_index = min(range(len(forecasts)), key=distances.__getitem__)
    closest = forecasts[closest_index]
    approaches = any(
        distance <= point.uncertainty_km
        for distance, point in zip(distances, forecasts, strict=True)
    )
    motion_span = (
        haversine_km(
            forecasts[0].latitude,
            forecasts[0].longitude,
            forecasts[-1].latitude,
            forecasts[-1].longitude,
        )
        if len(forecasts) > 1
        else 0.0
    )
    has_motion_evidence = motion_span >= 1.0

    if approaches and has_motion_evidence and distances[closest_index] <= closest.uncertainty_km:
        eta = closest.valid_at
        explanation = (
            "Target intersects the forecast uncertainty corridor; ETA is the closest "
            "discrete forecast time, not an exact operational warning."
        )
    elif approaches:
        eta = None
        explanation = (
            "Target is inside forecast uncertainty, but insufficient motion evidence "
            "prevents an exact ETA."
        )
    else:
        eta = None
        explanation = "Target remains outside the forecast uncertainty corridor."

    return ETAResult(
        approaches_target=approaches,
        closest_distance_km=distances[closest_index],
        closest_lead_minutes=closest.lead_minutes,
        uncertainty_km=closest.uncertainty_km,
        estimated_arrival=eta,
        explanation=explanation,
    )
