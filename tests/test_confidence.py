from storm_nowcast.confidence.framework import estimate_forecast_confidence
from storm_nowcast.tracking.twin import build_multisensor_twin
from tests.test_multisensor_twin import _cell


def test_confidence_is_qualitative_explainable_and_decreases_with_horizon():
    twin = build_multisensor_twin(_cell(), [])

    near = estimate_forecast_confidence(twin, lead_minutes=30)
    far = estimate_forecast_confidence(twin, lead_minutes=120)

    assert near.kind == "HEURISTIC_QUALITY"
    assert near.score is not None
    assert far.score < near.score
    assert far.label in {"LOW", "MODERATE"}
    assert any("missing" in reason.lower() for reason in far.reasons)
    assert near.calibration_version is None
