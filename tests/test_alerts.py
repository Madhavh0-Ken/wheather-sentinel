from datetime import datetime, timezone

from storm_nowcast.alerts.engine import AlertEngine, AlertRule, alerts_to_json
from storm_nowcast.hazards.registry import HazardAssessment
from storm_nowcast.models.schemas import ETAResult


def _hazard(status="SUPPORTED_HEURISTIC"):
    return HazardAssessment(
        hazard="EXTREME_RAIN",
        status=status,
        model_name="Prototype Extreme Rain Risk",
        score=80 if status == "SUPPORTED_HEURISTIC" else None,
        risk_label="HIGH" if status == "SUPPORTED_HEURISTIC" else None,
        explanation="Test heuristic assessment.",
    )


def test_alert_rule_fires_once_and_serializes_explanation():
    engine = AlertEngine(
        [AlertRule(rule_id="rain-near-target", hazard="EXTREME_RAIN", risk_levels={"HIGH"}, minimum_confidence="MODERATE")]
    )
    eta = ETAResult(
        approaches_target=True,
        closest_distance_km=8,
        closest_lead_minutes=30,
        uncertainty_km=20,
        estimated_arrival=datetime(2023, 7, 9, 1, tzinfo=timezone.utc),
        explanation="Target is inside heuristic corridor.",
    )
    issued = datetime(2023, 7, 9, tzinfo=timezone.utc)

    first = engine.evaluate(
        track_id="IPC-001", target="Shimla", source_timestamp=issued, hazards=[_hazard()], eta=eta,
        confidence="MODERATE",
    )
    second = engine.evaluate(
        track_id="IPC-001", target="Shimla", source_timestamp=issued, hazards=[_hazard()], eta=eta,
        confidence="MODERATE",
    )

    assert len(first) == 1
    assert second == []
    assert first[0].hazard == "EXTREME_RAIN"
    payload = alerts_to_json(first)
    assert '"storm_id": "IPC-001"' in payload
    assert "Test heuristic assessment" in payload


def test_alert_engine_suppresses_unsupported_or_insufficient_hazard():
    rule = AlertRule(rule_id="rain", hazard="EXTREME_RAIN", risk_levels={"HIGH"})
    engine = AlertEngine([rule])
    eta = ETAResult(approaches_target=True, closest_distance_km=3, explanation="test")

    assert engine.evaluate(
        track_id="IPC-001",
        target="Shimla",
        source_timestamp=datetime(2023, 7, 9, tzinfo=timezone.utc),
        hazards=[_hazard("INSUFFICIENT_DATA")],
        eta=eta,
        confidence="HIGH",
    ) == []
