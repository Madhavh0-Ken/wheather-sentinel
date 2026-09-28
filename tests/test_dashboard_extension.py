from datetime import datetime, timezone

from storm_nowcast.config import load_settings
from storm_nowcast.eta.calculator import calculate_eta
from storm_nowcast.nowcast.motion import forecast_track
from storm_nowcast.visualization.panels import (
    hazard_rows,
    resolve_operating_mode,
    satellite_evidence_rows,
    sensor_availability_rows,
)
from tests.test_motion import moving_track
from tests.test_replay import replay_dataset, satellite_cube
from storm_nowcast.replay.player import ReplayPlayer


def test_live_mode_gracefully_falls_back_when_no_official_live_source_is_configured():
    state = resolve_operating_mode("Live Mode", live_enabled=False, live_sources_available=False)

    assert state.actual == "Historical Replay"
    assert state.fallback is True
    assert "no official live provider" in state.message.lower()


def test_sensor_panel_distinguishes_real_available_and_unavailable_sources():
    snapshot = ReplayPlayer(
        replay_dataset(), load_settings(), satellite_cube=satellite_cube()
    ).analyze(1, target=(30.1, 75.3))
    rows = sensor_availability_rows(snapshot.timestamp, snapshot.insat)
    by_sensor = {row["Sensor"]: row for row in rows}

    assert len(rows) == 6
    assert by_sensor["CMORPH rainfall"]["State"] == "REAL"
    assert by_sensor["CMORPH rainfall"]["Availability"] == "AVAILABLE"
    assert "~8 km grid" in by_sensor["CMORPH rainfall"]["Native resolution"]
    assert "coarser" in by_sensor["CMORPH rainfall"]["Native resolution"]
    assert by_sensor["INSAT-3DR satellite"]["State"] == "REAL"
    assert by_sensor["INSAT-3DR satellite"]["Availability"] == "AVAILABLE"
    assert by_sensor["INSAT-3DR satellite"]["Observation UTC"] == "2023-07-09 00:15 UTC"
    assert by_sensor["INSAT-3DR satellite"]["Age"] == "15 min"
    assert by_sensor["INSAT-3DR satellite"]["Product"] == "3RIMG_L1C_ASIA_MER"
    assert by_sensor["IMD radar"]["Availability"] == "MANUAL OFFICIAL FILE REQUIRED"
    assert by_sensor["IMD lightning"]["State"] == "UNAVAILABLE"
    assert by_sensor["AWS/ARG"]["State"] == "UNAVAILABLE"
    assert by_sensor["NWP"]["State"] == "UNAVAILABLE"


def test_satellite_evidence_rows_disclose_channel_calibration_coverage_and_provenance():
    snapshot = ReplayPlayer(
        replay_dataset(), load_settings(), satellite_cube=satellite_cube()
    ).analyze(1, target=(30.1, 75.3))

    rows = satellite_evidence_rows(snapshot.insat)
    by_channel = {row["Source channel"]: row for row in rows}

    assert set(by_channel) == {"IMG_TIR1", "IMG_WV"}
    assert by_channel["IMG_TIR1"]["Variable"] == "infrared_brightness_temperature"
    assert by_channel["IMG_TIR1"]["Units"] == "K"
    assert by_channel["IMG_TIR1"]["Calibration LUT"] == "IMG_TIR1_TEMP"
    assert by_channel["IMG_TIR1"]["Native resolution"] == "4 km"
    assert by_channel["IMG_TIR1"]["Coverage"] == "12 / 12 valid samples"
    assert snapshot.insat.source_record_id.startswith("sha256:")


def test_sensor_panel_marks_missing_insat_unavailable_without_carry_forward():
    rows = sensor_availability_rows(datetime(2023, 7, 9, tzinfo=timezone.utc))
    insat = next(row for row in rows if row["Sensor"] == "INSAT-3DR satellite")

    assert insat["State"] == "UNAVAILABLE"
    assert insat["Availability"] == "UNAVAILABLE"
    assert insat["Observation UTC"] == "—"
    assert insat["Age"] == "—"


def test_hazard_panel_reports_unavailable_instead_of_zero_risk():
    cell = moving_track()
    rows = {row["Hazard"]: row for row in hazard_rows(cell)}

    assert rows["Extreme rain"]["Model state"] == "SUPPORTED HEURISTIC"
    assert rows["Hail"]["Model state"] == "INSUFFICIENT DATA"
    assert rows["Hail"]["Output"] == "Unavailable"
    assert rows["Downburst"]["Output"] == "Unavailable"
    assert rows["Lightning"]["Output"] == "Unavailable"
