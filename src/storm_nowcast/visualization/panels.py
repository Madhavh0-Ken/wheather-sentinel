from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from storm_nowcast.hazards.registry import assess_hazards
from storm_nowcast.models.schemas import StormCell
from storm_nowcast.replay.player import SatelliteFrameEvidence


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


def sensor_availability_rows(
    observation_time: datetime,
    insat: SatelliteFrameEvidence | None = None,
) -> list[dict[str, str]]:
    timestamp = observation_time.strftime("%Y-%m-%d %H:%M UTC")
    insat_available = bool(insat and insat.available)
    insat_timestamp = (
        insat.observation_time.strftime("%Y-%m-%d %H:%M UTC")
        if insat_available and insat and insat.observation_time
        else "—"
    )
    insat_age = (
        f"{insat.age_minutes:g} min"
        if insat_available and insat and insat.age_minutes is not None
        else "—"
    )
    return [
        {
            "Sensor": "CMORPH rainfall",
            "State": "REAL",
            "Availability": "AVAILABLE",
            "Observation UTC": timestamp,
            "Age": "0 min",
            "Product": "CMORPH V0.x RAW 8km-30min",
            "Native resolution": "~8 km grid; effective resolution is coarser",
            "Processed resolution": "Native source grid (no upsampling)",
        },
        {
            "Sensor": "INSAT-3DR satellite",
            "State": "REAL" if insat_available else "UNAVAILABLE",
            "Availability": "AVAILABLE" if insat_available else "UNAVAILABLE",
            "Observation UTC": insat_timestamp,
            "Age": insat_age,
            "Product": insat.product if insat_available and insat and insat.product else "—",
            "Native resolution": "4 km (product metadata)" if insat_available else "—",
            "Processed resolution": (
                "Native source grid (no artificial upscaling)" if insat_available else "Not available"
            ),
        },
        {
            "Sensor": "IMD radar",
            "State": "UNAVAILABLE",
            "Availability": "MANUAL OFFICIAL FILE REQUIRED",
            "Observation UTC": "—",
            "Age": "—",
            "Product": "—",
            "Native resolution": "Product metadata required",
            "Processed resolution": "Not processed",
        },
        {
            "Sensor": "IMD lightning",
            "State": "UNAVAILABLE",
            "Availability": "MANUAL OFFICIAL FILE REQUIRED",
            "Observation UTC": "—",
            "Age": "—",
            "Product": "—",
            "Native resolution": "Event locations; official metadata required",
            "Processed resolution": "Not processed",
        },
        {
            "Sensor": "AWS/ARG",
            "State": "UNAVAILABLE",
            "Availability": "MANUAL OFFICIAL FILE REQUIRED",
            "Observation UTC": "—",
            "Age": "—",
            "Product": "—",
            "Native resolution": "Station metadata required",
            "Processed resolution": "Not processed",
        },
        {
            "Sensor": "NWP",
            "State": "UNAVAILABLE",
            "Availability": "OFFICIAL DATASET REQUIRED",
            "Observation UTC": "—",
            "Age": "—",
            "Product": "—",
            "Native resolution": "Model metadata required",
            "Processed resolution": "Not processed",
        },
    ]


def satellite_evidence_rows(insat: SatelliteFrameEvidence) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for variable in insat.variables:
        valid = variable.total_pixel_count - variable.missing_pixel_count
        resolution = variable.native_spatial_resolution_km
        rows.append(
            {
                "Variable": variable.name,
                "Source channel": variable.source_variable,
                "Units": variable.units,
                "Calibration LUT": variable.calibration_lookup_table or "—",
                "Native resolution": f"{resolution:g} km" if resolution is not None else "—",
                "Coverage": f"{valid} / {variable.total_pixel_count} valid samples",
                "Availability": "AVAILABLE" if variable.available else "UNAVAILABLE",
            }
        )
    return rows


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
