from pathlib import Path
from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

import app
from storm_nowcast.events.custom import CustomEventRequest, EventLibraryRecord


def test_missing_event_message_names_recovery_command(tmp_path: Path):
    message = app.event_status_message(tmp_path / "missing.nc")

    assert "No prepared CMORPH event" in message
    assert "python scripts/prepare_demo.py" in message


def test_observation_mode_is_derived_from_cached_event_availability(tmp_path: Path):
    event = tmp_path / "event.nc"

    assert app.observation_mode(event) == ("EVENT DATA MISSING", "missing")
    event.write_bytes(b"cached")
    assert app.observation_mode(event) == ("CACHED HISTORICAL EVENT", "cached")


def test_streamlit_app_executes_without_uncaught_exception():
    result = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)

    assert not result.exception
    assert result.title[0].value == "StormNowcast"


def test_event_labels_and_full_day_request_summary_are_operationally_explicit(tmp_path):
    record = EventLibraryRecord(
        event_id="custom-event",
        display_name="Kerala window",
        kind="custom",
        data_path=tmp_path / "event.nc",
        ready=True,
        start_time=datetime(2023, 7, 9, tzinfo=timezone.utc),
        end_time=datetime(2023, 7, 10, tzinfo=timezone.utc),
        frame_count=49,
    )
    request = CustomEventRequest(
        min_lat=8, max_lat=18, min_lon=74, max_lon=84,
        start_time=record.start_time, end_time=record.end_time,
    )

    assert app.event_option_label(record) == "Custom | Kerala window"
    summary = app.request_summary(request)
    assert summary["observations"] == 49
    assert summary["source_hours"] == 25
    assert summary["span"] == "24h 00m inclusive"


def test_target_outside_event_bounds_is_detected():
    from storm_nowcast.config import Bounds

    bounds = Bounds(min_lat=8, max_lat=12, min_lon=74, max_lon=78)
    assert app.target_outside_bounds((10, 76), bounds) is False
    assert app.target_outside_bounds((13, 76), bounds) is True


def test_analyze_new_region_workflow_is_present_without_starting_download():
    result = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)

    assert "Analyze New Region" in result.sidebar.radio[0].options
    result.sidebar.radio[0].set_value("Analyze New Region").run(timeout=30)

    assert any("Prepare a CMORPH region" in item.value for item in result.subheader)
    assert any(button.label == "Download & Analyze" for button in result.button)
    assert not result.exception
