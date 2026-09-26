from __future__ import annotations

from storm_nowcast.models.schemas import RiskAssessment, StormCell


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def score_extreme_rain_risk(cell: StormCell) -> RiskAssessment:
    duration_hours = max(0.0, (cell.last_seen - cell.first_seen).total_seconds() / 3600)
    factors = {
        "intensity": _clamp(cell.current.max_intensity / 60.0),
        "trend": _clamp(cell.intensity_trend_mm_hr_per_hour / 20.0),
        "persistence": _clamp(duration_hours / 3.0),
        "slow_movement": _clamp(1.0 - cell.speed_kmh / 60.0),
        "growth": _clamp(cell.growth_trend_km2_per_hour / 100.0),
    }
    score = round(
        100
        * (
            0.40 * factors["intensity"]
            + 0.20 * factors["trend"]
            + 0.15 * factors["persistence"]
            + 0.15 * factors["slow_movement"]
            + 0.10 * factors["growth"]
        ),
        1,
    )
    if score >= 75:
        level = "VERY HIGH"
    elif score >= 55:
        level = "HIGH"
    elif score >= 30:
        level = "MODERATE"
    else:
        level = "LOW"

    contributors: list[str] = []
    if cell.current.max_intensity >= 40:
        contributors.append("high current rainfall")
    if cell.intensity_trend_mm_hr_per_hour >= 5:
        contributors.append("increasing intensity")
    if duration_hours >= 1:
        contributors.append("persistent cell")
    if cell.speed_kmh <= 15:
        contributors.append("slow movement")
    if cell.growth_trend_km2_per_hour >= 20:
        contributors.append("growing footprint")
    if not contributors:
        contributors.append("limited prototype risk signals")
    return RiskAssessment(score=score, level=level, contributors=contributors, factors=factors)
