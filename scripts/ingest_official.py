from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from storm_nowcast.config import Bounds
from storm_nowcast.data.lightning import load_imd_lightning_file
from storm_nowcast.data.nwp import load_official_nwp_file
from storm_nowcast.data.radar import load_imd_radar_file
from storm_nowcast.data.satellite import load_insat3dr_l1c_asia_mer, load_mosdac_file
from storm_nowcast.data.stations import load_imd_station_file
from storm_nowcast.models.sensors import SourceDescriptor, SpatialResolution


def parse_assignments(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Mappings must use NAME=SOURCE_NAME")
        name, source_name = (part.strip() for part in value.split("=", 1))
        if not name or not source_name:
            raise ValueError("Mappings must use NAME=SOURCE_NAME")
        if name in result:
            raise ValueError(f"Duplicate mapping for {name}")
        result[name] = source_name
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Import a user-supplied authoritative weather file without guessing its variables."
    )
    command.add_argument(
        "--source",
        required=True,
        choices=(
            "mosdac",
            "mosdac-insat3dr-l1c",
            "imd-radar",
            "imd-lightning",
            "imd-surface",
            "nwp",
        ),
    )
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--variable", action="append", default=[], help="Canonical grid variable=source variable")
    command.add_argument("--column", action="append", default=[], help="Canonical point column=source column")
    command.add_argument("--unit", action="append", default=[], help="Canonical variable=unit")
    command.add_argument("--native-resolution-km", type=float)
    command.add_argument("--min-lat", type=float, default=29.0)
    command.add_argument("--max-lat", type=float, default=33.0)
    command.add_argument("--min-lon", type=float, default=75.0)
    command.add_argument("--max-lon", type=float, default=79.0)
    command.add_argument("--provider")
    command.add_argument("--product")
    command.add_argument("--official-url")
    command.add_argument("--confirm-official-origin", action="store_true", required=True)
    return command


def main() -> None:
    args = parser().parse_args()
    bounds = Bounds(min_lat=args.min_lat, max_lat=args.max_lat, min_lon=args.min_lon, max_lon=args.max_lon)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.source == "mosdac-insat3dr-l1c":
        product = load_insat3dr_l1c_asia_mer(
            args.input,
            bounds=bounds,
            confirmed_official_origin=True,
        )
        product.dataset.to_netcdf(args.output, engine="h5netcdf")
        metadata = {
            "asset": product.asset.model_dump(mode="json"),
            "lineage": {name: item.model_dump(mode="json") for name, item in product.lineage.items()},
            "temporal_support": product.temporal_support.model_dump(mode="json"),
        }
    elif args.source in {"mosdac", "imd-radar", "nwp"}:
        if not args.native_resolution_km:
            raise SystemExit("--native-resolution-km is required for gridded products")
        variable_map = parse_assignments(args.variable)
        resolution = SpatialResolution(grid_spacing_km=args.native_resolution_km)
        if args.source == "mosdac":
            product = load_mosdac_file(
                args.input, bounds=bounds, variable_map=variable_map, native_resolution=resolution,
                confirmed_official_origin=True,
            )
        elif args.source == "imd-radar":
            product = load_imd_radar_file(
                args.input, bounds=bounds, variable_map=variable_map, native_resolution=resolution,
                confirmed_official_origin=True,
            )
        else:
            if not all((args.provider, args.product, args.official_url)):
                raise SystemExit("NWP import requires --provider, --product, and --official-url")
            descriptor = SourceDescriptor(
                provider=args.provider,
                product=args.product,
                sensor="NWP",
                official_url=args.official_url,
                access_method="manual official-file import",
            )
            product = load_official_nwp_file(
                args.input, source=descriptor, bounds=bounds, variable_map=variable_map,
                native_resolution=resolution, confirmed_official_origin=True,
            )
        product.dataset.to_netcdf(args.output, engine="h5netcdf")
        metadata = {
            "asset": product.asset.model_dump(mode="json"),
            "lineage": {name: item.model_dump(mode="json") for name, item in product.lineage.items()},
            "temporal_support": product.temporal_support.model_dump(mode="json"),
        }
    else:
        column_map = parse_assignments(args.column)
        if args.source == "imd-lightning":
            product = load_imd_lightning_file(
                args.input, column_map=column_map, bounds=bounds, confirmed_official_origin=True
            )
        else:
            product = load_imd_station_file(
                args.input, column_map=column_map, units=parse_assignments(args.unit), bounds=bounds,
                confirmed_official_origin=True,
            )
        product.frame.to_csv(args.output, index=False)
        metadata = {"asset": product.asset.model_dump(mode="json"), "units": product.units}
    args.output.with_suffix(args.output.suffix + ".provenance.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"Imported {args.source} asset to {args.output}")


if __name__ == "__main__":
    main()
