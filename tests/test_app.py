from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

import app
from storm_nowcast.events.custom import CustomEventRequest, EventLibraryRecord, SizeUnit
from storm_nowcast.events.errors import EventErrorCode, EventOperationError


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


def test_kilometre_region_entry_supports_normal_study_area_sizes():
    result = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    result.sidebar.radio[0].set_value("Analyze New Region").run(timeout=30)
    size_unit = next(item for item in result.selectbox if item.label == "Size unit")
    size_unit.set_value(SizeUnit.KILOMETRES).run(timeout=30)

    width = next(item for item in result.number_input if item.label == "Width")
    height = next(item for item in result.number_input if item.label == "Height")
    width.set_value(100.0)
    height.set_value(200.0)
    result.run(timeout=30)

    assert not result.exception
    assert next(item for item in result.number_input if item.label == "Width").value == 100.0
    assert next(item for item in result.number_input if item.label == "Height").value == 200.0


def test_successful_region_preparation_transitions_to_selected_replay_without_widget_error():
    builtin = app.event_repository().list_events()[0]

    class FakeRepository:
        def __init__(self):
            self.events = [builtin]

        def list_events(self):
            return self.events

        def delete(self, event_id):
            self.events = [event for event in self.events if event.event_id != event_id]

    repository = FakeRepository()

    class FakeBuilder:
        def prepare(self, request, **_kwargs):
            event_id = "review-custom"
            repository.events.append(
                builtin.model_copy(
                    update={
                        "kind": "custom",
                        "event_id": event_id,
                        "display_name": "Review custom",
                        "bounding_box": request.bounds,
                    }
                )
            )
            return SimpleNamespace(
                manifest=SimpleNamespace(
                    event_id=event_id,
                    frame_count=3,
                    bounding_box=request.bounds,
                )
            )

    original_repository = app.event_repository
    original_builder = app.event_builder
    app.event_repository = lambda: repository
    app.event_builder = lambda: FakeBuilder()
    try:
        result = AppTest.from_string("import app\napp.main()").run(timeout=30)
        result.sidebar.radio[0].set_value("Analyze New Region").run(timeout=30)
        next(button for button in result.button if button.label == "Download & Analyze").click().run(
            timeout=30
        )
    finally:
        app.event_repository = original_repository
        app.event_builder = original_builder

    assert not result.exception
    assert result.sidebar.radio[0].value == "Historical Replay"
    assert result.sidebar.selectbox[0].value == "review-custom"


def test_confirmed_custom_event_deletion_returns_to_builtin_without_widget_error():
    builtin = app.event_repository().list_events()[0]

    class FakeRepository:
        def __init__(self):
            self.events = [
                builtin,
                builtin.model_copy(
                    update={
                        "kind": "custom",
                        "event_id": "review-custom",
                        "display_name": "Review custom",
                    }
                ),
            ]

        def list_events(self):
            return self.events

        def delete(self, event_id):
            self.events = [event for event in self.events if event.event_id != event_id]

    repository = FakeRepository()
    original_repository = app.event_repository
    app.event_repository = lambda: repository
    try:
        result = AppTest.from_string("import app\napp.main()").run(timeout=30)
        result.sidebar.selectbox[0].set_value("review-custom").run(timeout=30)
        result.sidebar.checkbox[0].check().run(timeout=30)
        next(
            button for button in result.sidebar.button if button.label == "Delete custom event"
        ).click().run(timeout=30)
    finally:
        app.event_repository = original_repository

    assert not result.exception
    assert result.sidebar.selectbox[0].value == builtin.event_id


def test_custom_event_deletion_failure_is_rendered_without_crashing_dashboard():
    builtin = app.event_repository().list_events()[0]

    class FailingRepository:
        def list_events(self):
            return [
                builtin,
                builtin.model_copy(
                    update={
                        "kind": "custom",
                        "event_id": "review-custom",
                        "display_name": "Review custom",
                    }
                ),
            ]

        def delete(self, _event_id):
            raise EventOperationError(
                EventErrorCode.EVENT_STORAGE_FAILED,
                "The custom event could not be removed from storage.",
            )

    original_repository = app.event_repository
    app.event_repository = lambda: FailingRepository()
    try:
        result = AppTest.from_string("import app\napp.main()").run(timeout=30)
        result.sidebar.selectbox[0].set_value("review-custom").run(timeout=30)
        result.sidebar.checkbox[0].check().run(timeout=30)
        next(
            button for button in result.sidebar.button if button.label == "Delete custom event"
        ).click().run(timeout=30)
    finally:
        app.event_repository = original_repository

    assert not result.exception
    assert any("could not be removed" in error.value.lower() for error in result.sidebar.error)
