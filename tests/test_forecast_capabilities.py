from storm_nowcast.nowcast.capabilities import describe_forecast_capabilities


def test_two_to_six_hour_ml_is_unavailable_without_real_training_data():
    capabilities = {item.horizon: item for item in describe_forecast_capabilities()}

    assert capabilities["0-2h"].status == "AVAILABLE_BASELINE"
    assert "deterministic" in capabilities["0-2h"].method.lower()
    assert capabilities["2-6h"].status == "TRAINING_DATA_REQUIRED"
    assert capabilities["2-6h"].method is None
    assert "event-grouped" in capabilities["2-6h"].explanation
