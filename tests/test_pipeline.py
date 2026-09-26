from pathlib import Path

import xarray as xr

from storm_nowcast.config import load_settings
from storm_nowcast.replay.player import ReplayPlayer, save_event
from tests.test_replay import replay_dataset


def test_compact_event_round_trip_preserves_provenance_and_runs_pipeline(tmp_path: Path):
    event_path = tmp_path / "event.nc"
    original = replay_dataset()

    save_event(original, event_path)
    loaded = xr.load_dataset(event_path, engine="h5netcdf")
    player = ReplayPlayer(loaded, load_settings())
    snapshot = player.analyze(2, target=(30.1, 75.3))

    assert loaded.attrs["provider"] == "SYNTHETIC TEST FIXTURE"
    assert bool(loaded.attrs["is_synthetic"]) is True
    assert event_path.stat().st_size < 100_000
    assert snapshot.tracks
    assert snapshot.tracks[0].risk is not None
    assert snapshot.eta_by_track["IPC-001"].closest_distance_km >= 0
