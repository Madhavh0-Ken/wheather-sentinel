import pytest

from storm_nowcast.lightning.analytics import detect_lightning_jump


def test_lightning_jump_separates_observed_counts_from_derived_trend():
    result = detect_lightning_jump([1, 2, 1, 12], window_minutes=5, sigma_multiplier=2.0, minimum_count=5)

    assert result.observed_current_count == 12
    assert result.observed_history == [1, 2, 1]
    assert result.derived_growth_count == 11
    assert result.jump_detected is True
    assert result.status == "DERIVED"
    assert result.threshold_count == pytest.approx(5.0)


def test_lightning_jump_requires_history_instead_of_fabricating_trend():
    result = detect_lightning_jump([8], window_minutes=5)

    assert result.jump_detected is None
    assert result.status == "INSUFFICIENT_DATA"
