import pytest

from storm_nowcast.initiation.scoring import score_convective_initiation


def test_ci_score_is_unavailable_for_cmorph_rainfall_alone():
    result = score_convective_initiation({"rain_rate": 25.0})

    assert result.status == "INSUFFICIENT_DATA"
    assert result.score is None
    assert "precursor" in result.explanation.lower()


def test_ci_score_is_explainable_and_not_a_probability():
    result = score_convective_initiation(
        {
            "cloud_top_cooling_rate_k_per_hour": 10.0,
            "radar_reflectivity_growth_dbz_per_hour": 5.0,
            "surface_relative_humidity_percent": 80.0,
        }
    )

    assert result.status == "SUPPORTED_HEURISTIC"
    assert result.score == pytest.approx(0.325)
    assert result.score_kind == "UNCALIBRATED_SCORE"
    assert "rapid cloud-top cooling" in result.contributors
    assert "increasing radar reflectivity" in result.contributors
    assert "0.325" not in result.explanation
