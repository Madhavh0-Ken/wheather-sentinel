from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import xarray as xr

from storm_nowcast.config import load_settings
from storm_nowcast.data.demo import prepare_event
from storm_nowcast.replay.player import ReplayPlayer


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a compact official CMORPH replay event")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()
    settings = load_settings(args.config)
    prepared = prepare_event(settings, allow_download=not args.no_download)
    dataset = xr.load_dataset(prepared.path, engine="h5netcdf")
    player = ReplayPlayer(dataset, settings)
    snapshot = player.analyze(
        max(0, player.frame_count - 3),
        (settings.target.latitude, settings.target.longitude),
    )
    print(f"Prepared: {prepared.path}")
    print(f"Event: {prepared.start.isoformat()} to {prepared.end.isoformat()}")
    print(f"Frames: {prepared.frame_count}; event score: {prepared.score:.1f}")
    print(f"Detected/tracked cells at demonstration frame: {len(snapshot.tracks)}")


if __name__ == "__main__":
    main()
