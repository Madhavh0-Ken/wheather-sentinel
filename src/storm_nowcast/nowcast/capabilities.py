from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ForecastCapability(BaseModel):
    horizon: Literal["0-2h", "2-6h"]
    status: Literal["AVAILABLE_BASELINE", "TRAINING_DATA_REQUIRED"]
    method: str | None
    explanation: str


def describe_forecast_capabilities() -> list[ForecastCapability]:
    return [
        ForecastCapability(
            horizon="0-2h",
            status="AVAILABLE_BASELINE",
            method="Deterministic centroid motion; optional phase-correlation raster advection",
            explanation="Prototype extrapolation with increasing heuristic uncertainty.",
        ),
        ForecastCapability(
            horizon="2-6h",
            status="TRAINING_DATA_REQUIRED",
            method=None,
            explanation=(
                "A 2â€“6 hour learned forecast requires synchronized multi-event observations, environmental context, "
                "and a chronological event-grouped train/validation/test split."
            ),
        ),
    ]
