from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from storm_nowcast.config import load_settings
from storm_nowcast.data.cmorph_cache import CmorphCache
from storm_nowcast.events.builder import CmorphEventBuilder
from storm_nowcast.events.custom import CustomEventRequest
from storm_nowcast.events.repository import EventRepository


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Prepare a bounded custom NOAA CMORPH event.")
    command.add_argument("--min-lat", type=float, required=True)
    command.add_argument("--max-lat", type=float, required=True)
    command.add_argument("--min-lon", type=float, required=True)
    command.add_argument("--max-lon", type=float, required=True)
    command.add_argument("--start", type=str, required=True, help="Inclusive timezone-aware UTC timestamp")
    command.add_argument("--end", type=str, required=True, help="Inclusive timezone-aware UTC timestamp")
    command.add_argument("--name")
    command.add_argument(
        "--offline",
        "--no-download",
        dest="offline",
        action="store_true",
        help="Require validated local source files",
    )
    command.add_argument("--config", type=Path)
    command.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "configs" / "events.yaml")
    command.add_argument("--cache-root", type=Path, default=PROJECT_ROOT / "data" / "raw" / "cmorph")
    command.add_argument("--custom-root", type=Path, default=PROJECT_ROOT / "data" / "events" / "custom")
    return command


def main(argv: list[str] | None = None, *, builder: CmorphEventBuilder | None = None) -> int:
    args = parser().parse_args(argv)
    active_builder = builder or CmorphEventBuilder(
        EventRepository(args.catalog, args.custom_root),
        CmorphCache(args.cache_root),
        load_settings(args.config),
    )
    request = CustomEventRequest(
        min_lat=args.min_lat,
        max_lat=args.max_lat,
        min_lon=args.min_lon,
        max_lon=args.max_lon,
        start_time=datetime.fromisoformat(args.start.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(args.end.replace("Z", "+00:00")),
        event_name=args.name,
    )
    prepared = active_builder.prepare(request, allow_download=not args.offline)
    print(
        json.dumps(
            {
                "created": prepared.created,
                "reused": prepared.reused,
                "manifest": prepared.manifest.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
