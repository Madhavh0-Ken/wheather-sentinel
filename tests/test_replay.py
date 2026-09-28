import json
from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from storm_nowcast.config import load_settings
from storm_nowcast.replay.player import ReplayPlayer, score_event


def replay_dataset():
    times = np.array(
        ["2023-07-09T00:00", "2023-07-09T00:30", "2023-07-09T01:00"],
        dtype="datetime64[ns]",
    )
    rain = np.zeros((3, 3, 4), dtype=np.float32)
    rain[0, 1, 0:2] = [15, 20]
    rain[1, 1, 1:3] = [20, 25]
    rain[2, 1, 2:4] = [25, 30]
    return xr.Dataset(
        {
            "rain_rate": (("time", "latitude", "longitude"), rain),
            "missing_mask": (("time", "latitude", "longitude"), np.isnan(rain)),
        },
        coords={"time": times, "latitude": [30.0, 30.1, 30.2], "longitude": [75.0, 75.1, 75.2, 75.3]},
        attrs={
            "provider": "SYNTHETIC TEST FIXTURE",
            "product": "SYNTHETIC",
            "is_synthetic": True,
            "source_resolution": "0.1 degree test grid",
        },
    )


def satellite_cube(*, all_missing: bool = False):
    times = replay_dataset().time.values
    values = np.full((3, 3, 4), np.nan if all_missing else 235.0, dtype=float)
    provenance = json.dumps(
        {
            "asset": {
                "path": "data/manual/mosdac_satellite/source.h5",
                "sha256": "a" * 64,
                "source": {
                    "provider": "ISRO/SAC MOSDAC",
                    "product": "3RIMG_L1C_ASIA_MER",
                },
            }
        }
    )
    cube = xr.Dataset(
        {
            "infrared_brightness_temperature": (("time", "y", "x"), values),
            "infrared_brightness_temperature__missing": (
                ("time", "y", "x"),
                ~np.isfinite(values),
            ),
            "water_vapour_brightness_temperature": (("time", "y", "x"), values + 10.0),
            "water_vapour_brightness_temperature__missing": (
                ("time", "y", "x"),
                ~np.isfinite(values),
            ),
            "infrared_brightness_temperature__observation_time": (
                "time",
                times - np.timedelta64(15, "m"),
            ),
            "infrared_brightness_temperature__age_minutes": ("time", [15.0, 15.0, 15.0]),
            "infrared_brightness_temperature__available": ("time", [True, True, True]),
            "infrared_brightness_temperature__source_file": (
                "time",
                ["scan-2345.nc", "scan-0015.nc", "scan-0045.nc"],
            ),
            "infrared_brightness_temperature__source_record_id": (
                "time",
                ["sha256:" + "a" * 64] * 3,
            ),
            "infrared_brightness_temperature__provenance": ("time", [provenance] * 3),
            "water_vapour_brightness_temperature__observation_time": (
                "time",
                times - np.timedelta64(15, "m"),
            ),
            "water_vapour_brightness_temperature__age_minutes": ("time", [15.0, 15.0, 15.0]),
            "water_vapour_brightness_temperature__available": ("time", [True, True, True]),
            "water_vapour_brightness_temperature__source_file": (
                "time",
                ["scan-2345.nc", "scan-0015.nc", "scan-0045.nc"],
            ),
            "water_vapour_brightness_temperature__source_record_id": (
                "time",
                ["sha256:" + "a" * 64] * 3,
            ),
            "water_vapour_brightness_temperature__provenance": ("time", [provenance] * 3),
        },
        coords={
            "time": times,
            "y": np.arange(3),
            "x": np.arange(4),
            "latitude": ("y", [30.0, 30.1, 30.2]),
            "longitude": ("x", [75.0, 75.1, 75.2, 75.3]),
        },
        attrs={
            "provider": "ISRO/SAC MOSDAC",
            "product": "3RIMG_L1C_ASIA_MER",
            "max_age_minutes": 30,
            "spatial_alignment": "native source grid; no artificial upscaling",
        },
    )
    for variable, source, lookup in (
        ("infrared_brightness_temperature", "IMG_TIR1", "IMG_TIR1_TEMP"),
        ("water_vapour_brightness_temperature", "IMG_WV", "IMG_WV_TEMP"),
    ):
        cube[variable].attrs.update(
            {
                "provider": "ISRO/SAC MOSDAC",
                "product": "3RIMG_L1C_ASIA_MER",
                "units": "K",
                "source_variable": source,
                "calibration_lookup_table": lookup,
                "native_spatial_resolution_km": 4.0,
                "source_record_ids": json.dumps(["sha256:" + "a" * 64]),
            }
        )
    return cube


def test_event_score_rewards_intense_temporally_continuous_frames():
    wet = replay_dataset()
    dry = wet.copy(deep=True)
    dry.rain_rate.values[:] = 0

    assert score_event(wet, threshold_mm_hr=10) > score_event(dry, threshold_mm_hr=10)


def test_replay_uses_only_observations_at_or_before_selected_frame():
    player = ReplayPlayer(replay_dataset(), load_settings())
    snapshot = player.analyze(1, target=(30.1, 75.3))

    assert snapshot.frame_index == 1
    assert snapshot.timestamp == datetime(2023, 7, 9, 0, 30, tzinfo=timezone.utc)
    assert len(snapshot.observation_times) == 2
    assert max(snapshot.observation_times) <= snapshot.timestamp
    assert all(track.last_seen <= snapshot.timestamp for track in snapshot.tracks)
    assert snapshot.tracks[0].id == "IPC-001"
    assert [forecast.lead_minutes for forecast in snapshot.tracks[0].forecasts] == [30, 60, 120]


def test_replay_rejects_frame_outside_event():
    player = ReplayPlayer(replay_dataset(), load_settings())
    with pytest.raises(IndexError, match="frame index"):
        player.analyze(3, target=(30.1, 75.3))


def test_single_observation_track_has_no_motion_forecast_or_eta_claim():
    player = ReplayPlayer(replay_dataset(), load_settings())

    snapshot = player.analyze(0, target=(30.1, 75.3))

    assert len(snapshot.tracks[0].history) == 1
    assert snapshot.tracks[0].forecasts == []
    eta = snapshot.eta_by_track[snapshot.tracks[0].id]
    assert eta.estimated_arrival is None
    assert eta.closest_distance_km is None
    assert "Insufficient temporal history" in eta.explanation


def test_replay_exposes_selected_insat_frame_and_track_evidence():
    player = ReplayPlayer(replay_dataset(), load_settings(), satellite_cube=satellite_cube())

    snapshot = player.analyze(1, target=(30.1, 75.3))

    assert snapshot.insat.available is True
    assert snapshot.insat.observation_time == datetime(2023, 7, 9, 0, 15, tzinfo=timezone.utc)
    assert snapshot.insat.age_minutes == 15.0
    assert snapshot.insat.provider == "ISRO/SAC MOSDAC"
    assert snapshot.insat.product == "3RIMG_L1C_ASIA_MER"
    assert snapshot.insat.source_file == "scan-0015.nc"
    assert snapshot.insat.provenance["asset"]["sha256"] == "a" * 64
    summaries = {item.name: item for item in snapshot.insat.variables}
    assert summaries["infrared_brightness_temperature"].source_variable == "IMG_TIR1"
    assert summaries["infrared_brightness_temperature"].units == "K"
    assert summaries["infrared_brightness_temperature"].missing_pixel_count == 0
    assert summaries["water_vapour_brightness_temperature"].source_variable == "IMG_WV"
    assert snapshot.insat.data is not None
    assert "infrared_brightness_temperature__missing" in snapshot.insat.data
    evidence = snapshot.sensor_evidence_by_track[snapshot.tracks[0].id]
    assert len(evidence) == 1
    assert evidence[0].sensor == "SATELLITE"
    assert evidence[0].variables == {
        "infrared_brightness_temperature": 235.0,
        "water_vapour_brightness_temperature": 245.0,
    }
    assert evidence[0].source_record_ids == ["sha256:" + "a" * 64]


def test_replay_marks_absent_or_all_missing_insat_evidence_unavailable():
    absent = ReplayPlayer(replay_dataset(), load_settings()).analyze(1, target=(30.1, 75.3))
    missing = ReplayPlayer(
        replay_dataset(), load_settings(), satellite_cube=satellite_cube(all_missing=True)
    ).analyze(1, target=(30.1, 75.3))

    for snapshot in (absent, missing):
        assert snapshot.insat.available is False
        assert snapshot.sensor_evidence_by_track[snapshot.tracks[0].id] == []
