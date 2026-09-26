from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storm_nowcast.data.download import download_file
from storm_nowcast.data.sources import CmorphSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one official NOAA CPC CMORPH hourly file")
    parser.add_argument("timestamp", help="UTC hour, for example 2023-07-09T06:00:00Z")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/cmorph"))
    args = parser.parse_args()
    timestamp = datetime.fromisoformat(args.timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    source = CmorphSource()
    url = source.build_url(timestamp)
    destination = args.output_dir / Path(url).name
    result = download_file(url, destination)
    print(f"{result.path} sha256={result.sha256} downloaded={result.downloaded}")


if __name__ == "__main__":
    main()
