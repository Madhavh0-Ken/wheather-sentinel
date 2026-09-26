from __future__ import annotations

from storm_nowcast.models.schemas import StormCell
from storm_nowcast.models.sensors import SensorKind
from storm_nowcast.models.twin import MultiSensorStormCell, SensorEvidence
from storm_nowcast.tracking.tracker import haversine_km


SENSOR_KINDS: tuple[SensorKind, ...] = (
    "RAINFALL",
    "SATELLITE",
    "RADAR",
    "LIGHTNING",
    "SURFACE",
    "NWP",
)


def _acceleration(cell: StormCell) -> float | None:
    if len(cell.history) < 3:
        return None
    first, second, third = cell.history[-3:]
    first_hours = (second.timestamp - first.timestamp).total_seconds() / 3600
    second_hours = (third.timestamp - second.timestamp).total_seconds() / 3600
    if first_hours <= 0 or second_hours <= 0:
        return None
    first_speed = haversine_km(first.centroid_lat, first.centroid_lon, second.centroid_lat, second.centroid_lon) / first_hours
    second_speed = haversine_km(second.centroid_lat, second.centroid_lon, third.centroid_lat, third.centroid_lon) / second_hours
    midpoint_hours = (first_hours + second_hours) / 2
    return (second_speed - first_speed) / midpoint_hours


def build_multisensor_twin(cell: StormCell, evidence: list[SensorEvidence]) -> MultiSensorStormCell:
    ordered = sorted(evidence, key=lambda item: item.timestamp)
    availability = {sensor: "UNAVAILABLE" for sensor in SENSOR_KINDS}
    availability["RAINFALL"] = "AVAILABLE"
    current_features: dict[str, float] = {}
    for item in ordered:
        availability[item.sensor] = "AVAILABLE"
        current_features.update(item.variables)
    return MultiSensorStormCell(
        baseline=cell,
        evidence_history=ordered,
        sensor_availability=availability,
        current_features=current_features,
        acceleration_kmh_per_hour=_acceleration(cell),
    )
