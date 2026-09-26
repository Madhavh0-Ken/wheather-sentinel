from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConvectiveInitiationAssessment(BaseModel):
    name: str = "Convective Initiation Score"
    status: Literal["SUPPORTED_HEURISTIC", "INSUFFICIENT_DATA"]
    score: float | None = Field(default=None, ge=0, le=1)
    score_kind: Literal["UNCALIBRATED_SCORE"] = "UNCALIBRATED_SCORE"
    contributors: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    explanation: str


def _positive(value: float | None, scale: float) -> float:
    return min(max(float(value or 0.0), 0.0) / scale, 1.0)


def score_convective_initiation(features: dict[str, float | None]) -> ConvectiveInitiationAssessment:
    precursor_keys = {
        "cloud_top_cooling_rate_k_per_hour",
        "radar_reflectivity_growth_dbz_per_hour",
        "lightning_growth_count_per_10min",
    }
    available_precursors = [key for key in precursor_keys if features.get(key) is not None]
    if not available_precursors:
        return ConvectiveInitiationAssessment(
            status="INSUFFICIENT_DATA",
            missing_inputs=sorted(precursor_keys),
            explanation=(
                "Convective Initiation Score requires at least one satellite, radar, or lightning precursor; "
                "rainfall alone does not establish pre-initiation convection."
            ),
        )
    contributors: list[str] = []
    score = 0.0
    cooling = _positive(features.get("cloud_top_cooling_rate_k_per_hour"), 20.0)
    if cooling:
        score += 0.4 * cooling
        contributors.append("rapid cloud-top cooling")
    radar_growth = _positive(features.get("radar_reflectivity_growth_dbz_per_hour"), 20.0)
    if radar_growth:
        score += 0.3 * radar_growth
        contributors.append("increasing radar reflectivity")
    lightning_growth = _positive(features.get("lightning_growth_count_per_10min"), 10.0)
    if lightning_growth:
        score += 0.2 * lightning_growth
        contributors.append("increasing lightning activity")
    humidity = features.get("surface_relative_humidity_percent")
    if humidity is not None:
        moisture = min(max((float(humidity) - 60.0) / 40.0, 0.0), 1.0)
        score += 0.1 * moisture
        if moisture:
            contributors.append("moist environmental context")
    return ConvectiveInitiationAssessment(
        status="SUPPORTED_HEURISTIC",
        score=min(score, 1.0),
        contributors=contributors,
        explanation="Explainable, uncalibrated precursor score; it is not a probability of convection.",
    )
