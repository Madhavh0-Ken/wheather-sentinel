from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from storm_nowcast.hazards.registry import HazardAssessment, HazardType
from storm_nowcast.models.schemas import ETAResult, _as_utc


ConfidenceLabel = Literal["LOW", "MODERATE", "HIGH"]
CONFIDENCE_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2}


class AlertRule(BaseModel):
    rule_id: str
    hazard: HazardType
    risk_levels: set[str]
    minimum_confidence: ConfidenceLabel = "LOW"
    approach_required: bool = True
    cooldown_minutes: int = Field(default=60, ge=0)


class AlertEvent(BaseModel):
    alert_id: str
    rule_id: str
    storm_id: str
    hazard: HazardType
    risk: str
    target: str
    forecast_time: datetime | None
    estimated_arrival: datetime | None
    confidence: ConfidenceLabel
    source_timestamp: datetime
    explanation: str

    _utc_times = field_validator("forecast_time", "estimated_arrival", "source_timestamp", mode="before")(
        lambda value: _as_utc(value) if value is not None else None
    )


class AlertEngine:
    def __init__(self, rules: list[AlertRule]) -> None:
        self.rules = rules
        self._last_issued: dict[tuple[str, str, str], datetime] = {}

    def evaluate(
        self,
        *,
        track_id: str,
        target: str,
        source_timestamp: datetime,
        hazards: list[HazardAssessment],
        eta: ETAResult,
        confidence: ConfidenceLabel,
    ) -> list[AlertEvent]:
        source_timestamp = _as_utc(source_timestamp)
        by_type = {item.hazard: item for item in hazards}
        emitted: list[AlertEvent] = []
        for rule in self.rules:
            hazard = by_type.get(rule.hazard)
            if hazard is None or hazard.status != "SUPPORTED_HEURISTIC":
                continue
            if hazard.risk_label not in rule.risk_levels:
                continue
            if rule.approach_required and not eta.approaches_target:
                continue
            if CONFIDENCE_ORDER[confidence] < CONFIDENCE_ORDER[rule.minimum_confidence]:
                continue
            key = (rule.rule_id, track_id, target)
            last = self._last_issued.get(key)
            if last is not None and source_timestamp - last < timedelta(minutes=rule.cooldown_minutes):
                continue
            self._last_issued[key] = source_timestamp
            digest = hashlib.sha256(f"{rule.rule_id}|{track_id}|{target}|{source_timestamp.isoformat()}".encode()).hexdigest()[:16]
            forecast_time = (
                source_timestamp + timedelta(minutes=eta.closest_lead_minutes)
                if eta.closest_lead_minutes is not None
                else None
            )
            emitted.append(
                AlertEvent(
                    alert_id=f"alert-{digest}",
                    rule_id=rule.rule_id,
                    storm_id=track_id,
                    hazard=hazard.hazard,
                    risk=hazard.risk_label or "UNAVAILABLE",
                    target=target,
                    forecast_time=forecast_time,
                    estimated_arrival=eta.estimated_arrival,
                    confidence=confidence,
                    source_timestamp=source_timestamp,
                    explanation=f"{hazard.explanation} {eta.explanation}".strip(),
                )
            )
        return emitted


def alerts_to_json(alerts: list[AlertEvent]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in alerts], indent=2)
