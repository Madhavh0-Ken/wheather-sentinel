from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from storm_nowcast.hazards.extreme_rain import score_extreme_rain_risk
from storm_nowcast.models.schemas import StormCell


HazardType = Literal["EXTREME_RAIN", "LIGHTNING", "HAIL", "DOWNBURST"]
HazardStatus = Literal["SUPPORTED_HEURISTIC", "INSUFFICIENT_DATA", "UNSUPPORTED", "NOT_APPLICABLE"]


class HazardAssessment(BaseModel):
    hazard: HazardType
    status: HazardStatus
    model_name: str
    score: float | None = Field(default=None, ge=0, le=100)
    risk_label: str | None = None
    score_kind: str | None = None
    contributors: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    explanation: str


def assess_hazards(cell: StormCell) -> list[HazardAssessment]:
    rain = cell.risk or score_extreme_rain_risk(cell)
    return [
        HazardAssessment(
            hazard="EXTREME_RAIN",
            status="SUPPORTED_HEURISTIC",
            model_name="Prototype Extreme Rain Risk",
            score=rain.score,
            risk_label=rain.level,
            score_kind="UNCALIBRATED_HEURISTIC",
            contributors=rain.contributors,
            explanation="Rainfall-derived heuristic; not validated cloudburst detection.",
        ),
        HazardAssessment(
            hazard="LIGHTNING",
            status="INSUFFICIENT_DATA",
            model_name="Lightning forecast unavailable",
            required_inputs=["verified historical lightning observations"],
            explanation="Lightning forecast requires verified observations and held-out validation.",
        ),
        HazardAssessment(
            hazard="HAIL",
            status="INSUFFICIENT_DATA",
            model_name="Hail model unavailable",
            required_inputs=["verified hail labels", "radar/satellite evidence"],
            explanation="Hail model unavailable â€” insufficient verified labels.",
        ),
        HazardAssessment(
            hazard="DOWNBURST",
            status="INSUFFICIENT_DATA",
            model_name="Downburst prediction unavailable",
            required_inputs=["verified downburst labels", "surface wind or radar velocity evidence"],
            explanation="Downburst prediction unavailable â€” verified training labels required.",
        ),
    ]
