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
