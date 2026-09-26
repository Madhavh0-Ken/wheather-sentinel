from datetime import datetime, timezone

from storm_nowcast.config import load_settings
from storm_nowcast.eta.calculator import calculate_eta
from storm_nowcast.nowcast.motion import forecast_track
from storm_nowcast.visualization.panels import (
    hazard_rows,
    resolve_operating_mode,
    sensor_availability_rows,
)
from tests.test_motion import moving_track


def test_live_mode_gracefully_falls_back_when_no_official_live_source_is_configured():
    state = resolve_operating_mode("Live Mode", live_enabled=False, live_sources_available=False)

    assert state.actual == "Historical Replay"
    assert state.fallback is True
    assert "no official live provider" in state.message.lower()


def test_sensor_panel_distinguishes_observed_and_unavailable_with_resolution_truth():
    rows = sensor_availability_rows(datetime(2023, 7, 9, tzinfo=timezone.utc))
    by_sensor = {row["Sensor"]: row for row in rows}

    assert by_sensor["CMORPH rainfall"]["State"] == "OBSERVED"
    assert by_sensor["CMORPH rainfall"]["Availability"] == "AVAILABLE"
    assert "~8 km grid" in by_sensor["CMORPH rainfall"]["Native resolution"]
    assert "coarser" in by_sensor["CMORPH rainfall"]["Native resolution"]
    assert by_sensor["INSAT satellite"]["State"] == "UNAVAILABLE"
    assert by_sensor["IMD radar"]["Availability"] == "MANUAL OFFICIAL FILE REQUIRED"
    assert by_sensor["IMD lightning"]["State"] == "UNAVAILABLE"


def test_hazard_panel_reports_unavailable_instead_of_zero_risk():
    cell = moving_track()
    rows = {row["Hazard"]: row for row in hazard_rows(cell)}

    assert rows["Extreme rain"]["Model state"] == "SUPPORTED HEURISTIC"
    assert rows["Hail"]["Model state"] == "INSUFFICIENT DATA"
    assert rows["Hail"]["Output"] == "Unavailable"
    assert rows["Downburst"]["Output"] == "Unavailable"
    assert rows["Lightning"]["Output"] == "Unavailable"
