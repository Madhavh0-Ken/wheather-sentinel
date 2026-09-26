from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from storm_nowcast.hazards.registry import assess_hazards
from storm_nowcast.models.schemas import StormCell


class OperatingModeState(BaseModel):
    requested: Literal["Historical Replay", "Live Mode"]
    actual: Literal["Historical Replay", "Live Mode"]
    fallback: bool
    message: str


def resolve_operating_mode(
    requested: Literal["Historical Replay", "Live Mode"],
    *,
    live_enabled: bool,
    live_sources_available: bool,
) -> OperatingModeState:
    if requested == "Live Mode" and not (live_enabled and live_sources_available):
        return OperatingModeState(
            requested=requested,
            actual="Historical Replay",
            fallback=True,
            message=(
                "Live Mode unavailable â€” no official live provider is configured and available. "
                "Showing the cached Historical Replay fallback."
            ),
        )
    return OperatingModeState(
        requested=requested,
        actual=requested,
        fallback=False,
        message=(
            "Polling configured official sources with cached last-valid fallback."
            if requested == "Live Mode"
            else "Replaying cached official observations causally."
        ),
    )


def sensor_availability_rows(observation_time: datetime) -> list[dict[str, str]]:
    timestamp = observation_time.strftime("%Y-%m-%d %H:%M UTC")
    return [
        {
            "Sensor": "CMORPH rainfall",
            "State": "OBSERVED",
            "Availability": "AVAILABLE",
            "Observation UTC": timestamp,
            "Native resolution": "~8 km grid; effective resolution is coarser",
            "Processed resolution": "Native source grid (no upsampling)",
        },
        {
            "Sensor": "INSAT satellite",
            "State": "UNAVAILABLE",
            "Availability": "AUTHENTICATED OFFICIAL FILE REQUIRED",
            "Observation UTC": "â€”",
            "Native resolution": "Product metadata required",
            "Processed resolution": "Not processed",
        },
        {
            "Sensor": "IMD radar",
            "State": "UNAVAILABLE",
            "Availability": "MANUAL OFFICIAL FILE REQUIRED",
            "Observation UTC": "â€”",
            "Native resolution": "Product metadata required",
            "Processed resolution": "Not processed",
        },
        {
            "Sensor": "IMD lightning",
            "State": "UNAVAILABLE",
            "Availability": "MANUAL OFFICIAL FILE REQUIRED",
            "Observation UTC": "â€”",
            "Native resolution": "Event locations; official metadata required",
            "Processed resolution": "Not processed",
        },
    ]


def hazard_rows(cell: StormCell) -> list[dict[str, str]]:
    names = {
        "EXTREME_RAIN": "Extreme rain",
        "LIGHTNING": "Lightning",
        "HAIL": "Hail",
        "DOWNBURST": "Downburst",
    }
    rows: list[dict[str, str]] = []
    for assessment in assess_hazards(cell):
        output = assessment.risk_label or "Unavailable"
        rows.append(
            {
                "Hazard": names[assessment.hazard],
                "Model state": assessment.status.replace("_", " "),
                "Output": output,
                "Explanation": assessment.explanation,
            }
        )
    return rows
