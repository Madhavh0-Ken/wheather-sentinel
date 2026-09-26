from storm_nowcast.hazards.registry import assess_hazards
from tests.test_motion import moving_track


def test_registry_keeps_extreme_rain_heuristic_and_marks_unsupported_hazards():
    assessments = {item.hazard: item for item in assess_hazards(moving_track())}

    assert assessments["EXTREME_RAIN"].status == "SUPPORTED_HEURISTIC"
    assert assessments["EXTREME_RAIN"].model_name == "Prototype Extreme Rain Risk"
    assert assessments["HAIL"].status == "INSUFFICIENT_DATA"
    assert "verified labels" in assessments["HAIL"].explanation
    assert assessments["DOWNBURST"].status == "INSUFFICIENT_DATA"
    assert assessments["LIGHTNING"].status == "INSUFFICIENT_DATA"
    assert all(item.score is None for key, item in assessments.items() if key != "EXTREME_RAIN")
