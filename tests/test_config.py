from pathlib import Path

import pytest

from storm_nowcast.config import Bounds, load_settings


def test_default_settings_use_compact_himachal_study_area():
    settings = load_settings()

    assert settings.study_area.name == "Himachal Pradesh and nearby north-west India"
    assert settings.study_area.bounds == Bounds(
        min_lat=29.0, max_lat=33.0, min_lon=75.0, max_lon=79.0
    )
    assert settings.forecast.lead_minutes == (30, 60, 120)


def test_yaml_overrides_nested_bounds(tmp_path: Path):
    config_file = tmp_path / "custom.yaml"
    config_file.write_text(
        "study_area:\n"
        "  name: Western Ghats\n"
        "  bounds:\n"
        "    min_lat: 10\n"
        "    max_lat: 14\n"
        "    min_lon: 74\n"
        "    max_lon: 78\n",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.study_area.name == "Western Ghats"
    assert settings.study_area.bounds.min_lat == 10.0
    assert settings.study_area.bounds.max_lon == 78.0
    assert settings.data.processed_event.name == "cmorph_india_event.nc"


def test_environment_overrides_yaml_for_nested_values(monkeypatch):
    monkeypatch.setenv("STORM_NOWCAST_DATA__MAX_FRAMES", "20")

    assert load_settings().data.max_frames == 20


@pytest.mark.parametrize(
    "values",
    [
        {"min_lat": 33, "max_lat": 29, "min_lon": 75, "max_lon": 79},
        {"min_lat": -91, "max_lat": 10, "min_lon": 75, "max_lon": 79},
        {"min_lat": 29, "max_lat": 33, "min_lon": 80, "max_lon": 79},
    ],
)
def test_bounds_reject_invalid_ranges(values):
    with pytest.raises(ValueError):
        Bounds(**values)
