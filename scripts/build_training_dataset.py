from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from storm_nowcast.events.catalog import load_event_catalog
from storm_nowcast.training.dataset import (
    DEFAULT_HISTORY_MINUTES,
    DEFAULT_LEAD_MINUTES,
    build_horizon_datasets,
    chronological_event_split,
    fit_training_normalization,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Build causal event-separated nowcast training artifacts without training a model."
    )
    command.add_argument("--catalog", type=Path, default=Path("configs/events.yaml"))
    command.add_argument("--output-dir", type=Path, default=Path("data/processed/training"))
    command.add_argument("--variable", default="rain_rate")
    return command


def build_training_artifacts(
    *,
    catalog_path: Path,
    output_dir: Path,
    variable: str = "rain_rate",
) -> dict[str, object]:
    catalog = load_event_catalog(catalog_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    event_datasets: dict[str, xr.Dataset] = {}
    event_records: list[dict[str, object]] = []
    missing_events: list[dict[str, str]] = []
    for event in catalog.events:
        if not event.data_path.exists():
            missing_events.append(
                {"event_id": event.id, "data_path": str(event.data_path), "reason": "file not found"}
            )
            continue
        dataset = xr.load_dataset(event.data_path, engine="h5netcdf")
        if dataset.sizes.get("time", 0) != event.frame_count:
            raise ValueError(
                f"Event {event.id} catalog frame_count={event.frame_count} does not match "
                f"dataset time size={dataset.sizes.get('time', 0)}"
            )
        event_datasets[event.id] = dataset
        event_records.append(
            {
                "event_id": event.id,
                "name": event.name,
                "region": event.region,
                "observation_start": event.observation_start.isoformat().replace("+00:00", "Z"),
                "observation_end": event.observation_end.isoformat().replace("+00:00", "Z"),
                "frame_count": event.frame_count,
                "sources": event.sources,
                "data_path": str(event.data_path),
                "is_synthetic": bool(dataset.attrs.get("is_synthetic", False)),
            }
        )
    if not event_datasets:
        raise ValueError("No available event datasets were found in the catalog")

    horizons = build_horizon_datasets(event_datasets, variable=variable)
    artifacts: dict[str, str | None] = {}
    for lead, horizon in horizons.items():
        artifact_path = output_dir / f"{variable}_lead_{lead:03d}.nc"
        if horizon.sample_count == 0:
            artifact_path.unlink(missing_ok=True)
            artifacts[str(lead)] = None
            continue
        horizon.to_xarray().to_netcdf(artifact_path, engine="h5netcdf")
        artifacts[str(lead)] = str(artifact_path)

    split_payload: dict[str, object]
    normalization_payload: dict[str, object]
    try:
        split = chronological_event_split(event_datasets)
    except ValueError as exc:
        split_payload = {"status": "UNAVAILABLE", "reason": str(exc)}
        normalization_payload = {
            "status": "UNAVAILABLE",
            "reason": "Train-only normalization requires an event-separated training split.",
        }
    else:
        split_payload = {
            "status": "AVAILABLE",
            "train_events": list(split.train_events),
            "validation_events": list(split.validation_events),
            "test_events": list(split.test_events),
        }
        statistics: dict[str, object] = {}
        for lead, horizon in horizons.items():
            if horizon.sample_count == 0:
                continue
            try:
                fitted = fit_training_normalization(horizon, split)
            except ValueError as exc:
                statistics[str(lead)] = {"status": "UNAVAILABLE", "reason": str(exc)}
            else:
                statistics[str(lead)] = {
                    "status": "AVAILABLE",
                    "mean": fitted.mean,
                    "standard_deviation": fitted.standard_deviation,
                    "fitted_event_ids": list(fitted.fitted_event_ids),
                }
        normalization_payload = {"status": "AVAILABLE", "by_horizon": statistics}

    event_count = len(event_datasets)
    if event_count < 3:
        model_reason = (
            "2–6 hour learned nowcast unavailable: additional synchronized historical events required."
        )
    else:
        model_reason = (
            "2–6 hour learned nowcast unavailable: model training and held-out evaluation have not been run."
        )
    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "variable": variable,
        "history_offsets_minutes": list(DEFAULT_HISTORY_MINUTES),
        "lead_minutes": list(DEFAULT_LEAD_MINUTES),
        "event_count": event_count,
        "events": event_records,
        "missing_events": missing_events,
        "sample_counts": {str(lead): horizon.sample_count for lead, horizon in horizons.items()},
        "artifacts": artifacts,
        "split": split_payload,
        "normalization": normalization_payload,
        "leakage_prevention": [
            "exact timestamps only; no temporal interpolation",
            "history times are at or before analysis time",
            "targets are after analysis time within the same event",
            "whole events are assigned chronologically to one split only",
            "temporally overlapping events across splits are rejected",
            "normalization is fitted from training inputs only",
        ],
        "learned_model": {"status": "UNAVAILABLE", "reason": model_reason},
    }
    manifest_path = output_dir / "training_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    args = parser().parse_args()
    manifest = build_training_artifacts(
        catalog_path=args.catalog,
        output_dir=args.output_dir,
        variable=args.variable,
    )
    print(f"Events: {manifest['event_count']}")
    print(f"Samples by lead: {manifest['sample_counts']}")
    print(f"Split: {manifest['split']['status']}")
    print(f"Learned model: {manifest['learned_model']['status']}")


if __name__ == "__main__":
    main()
