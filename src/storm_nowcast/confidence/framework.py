from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from storm_nowcast.models.twin import MultiSensorStormCell


class ConfidenceEstimate(BaseModel):
    label: Literal["LOW", "MODERATE", "HIGH"]
    score: float | None = Field(default=None, ge=0, le=1)
    kind: Literal["HEURISTIC_QUALITY", "CALIBRATED_PROBABILITY"] = "HEURISTIC_QUALITY"
    reasons: list[str]
    sample_count: int = Field(ge=0)
    calibration_version: str | None = None


def estimate_forecast_confidence(
    twin: MultiSensorStormCell,
    *,
    lead_minutes: int,
    recent_position_error_km: float | None = None,
) -> ConfidenceEstimate:
    score = 0.25
    reasons: list[str] = []
    history_count = len(twin.baseline.history)
    score += min(history_count / 5, 1.0) * 0.3
    reasons.append(f"{history_count} tracked observation states")
    if twin.baseline.bearing_deg is not None and twin.baseline.speed_kmh >= 1:
        score += 0.1
        reasons.append("stable non-stationary motion is available")
    available_optional = sum(
        state == "AVAILABLE" for sensor, state in twin.sensor_availability.items() if sensor != "RAINFALL"
    )
    score += available_optional / 5 * 0.15
    if available_optional == 0:
        reasons.append("optional satellite, radar, lightning, surface, and NWP sensors are missing")
    horizon_penalty = min(lead_minutes / 120, 1.5) * 0.35
    score -= horizon_penalty
    reasons.append(f"forecast lead is {lead_minutes} minutes")
    if recent_position_error_km is not None:
        score -= min(recent_position_error_km / 100, 1.0) * 0.2
        reasons.append(f"recent real-observation position error is {recent_position_error_km:.1f} km")
    score = min(max(score, 0.0), 1.0)
    label: Literal["LOW", "MODERATE", "HIGH"] = "HIGH" if score >= 0.7 else "MODERATE" if score >= 0.45 else "LOW"
    return ConfidenceEstimate(
        label=label,
        score=score,
        reasons=reasons,
        sample_count=history_count,
        calibration_version=None,
    )
