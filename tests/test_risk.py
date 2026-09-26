from tests.test_motion import moving_track

from storm_nowcast.hazards.extreme_rain import score_extreme_rain_risk


def test_risk_score_is_bounded_and_exposes_contributors():
    track = moving_track(speed=8)
    track.history[-1].max_intensity = 75
    track.intensity_trend_mm_hr_per_hour = 25
    track.growth_trend_km2_per_hour = 70

    risk = score_extreme_rain_risk(track)

    assert 0 <= risk.score <= 100
    assert risk.level in {"HIGH", "VERY HIGH"}
    assert "high current rainfall" in risk.contributors
    assert "increasing intensity" in risk.contributors
    assert "slow movement" in risk.contributors
    assert set(risk.factors) == {"intensity", "trend", "persistence", "slow_movement", "growth"}


def test_low_intensity_fast_short_lived_cell_has_low_risk():
    track = moving_track(speed=80)
    track.history[-1].max_intensity = 10
    track.intensity_trend_mm_hr_per_hour = -5
    track.growth_trend_km2_per_hour = -20

    risk = score_extreme_rain_risk(track)

    assert risk.level == "LOW"
    assert risk.score < 30
    assert risk.contributors == ["limited prototype risk signals"]
