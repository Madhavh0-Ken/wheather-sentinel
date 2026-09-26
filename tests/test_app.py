from pathlib import Path

from streamlit.testing.v1 import AppTest

import app


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
