import json
import subprocess
import sys
from datetime import datetime, timezone

import xarray as xr
import yaml

from tests.test_training_dataset import _event


def test_training_builder_writes_real_event_horizons_and_unavailable_split_manifest(tmp_path):
    event_id = "official-event"
    event_path = tmp_path / "data" / "processed" / "event.nc"
    event_path.parent.mkdir(parents=True)
    dataset = _event(event_id, datetime(2023, 7, 9, tzinfo=timezone.utc))
    dataset.attrs["is_synthetic"] = 0
    dataset.attrs["provider"] = "Authoritative test provider"
    dataset.to_netcdf(event_path, engine="h5netcdf")
    catalog_path = tmp_path / "configs" / "events.yaml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        yaml.safe_dump(
            {
                "events": [
                    {
                        "id": event_id,
                        "name": "Official event",
                        "region": "Test region",
                        "observation_start": "2023-07-09T00:00:00Z",
                        "observation_end": "2023-07-09T05:30:00Z",
                        "sources": ["Authoritative test provider"],
                        "frame_count": 12,
                        "data_path": "data/processed/event.nc",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "training"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_training_dataset.py",
            "--catalog",
            str(catalog_path),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["event_count"] == 1
    assert manifest["events"][0]["event_id"] == event_id
    assert manifest["sample_counts"] == {
        "30": 7,
        "60": 6,
        "120": 4,
        "180": 2,
        "360": 0,
    }
    assert manifest["split"]["status"] == "UNAVAILABLE"
    assert manifest["normalization"]["status"] == "UNAVAILABLE"
    assert manifest["learned_model"]["status"] == "UNAVAILABLE"
    assert "additional synchronized historical events required" in manifest["learned_model"]["reason"]
    assert not (output_dir / "rain_rate_lead_360.nc").exists()
    with xr.open_dataset(output_dir / "rain_rate_lead_030.nc", engine="h5netcdf") as horizon:
        assert horizon.sizes["sample"] == 7
        assert horizon.event_id.values.tolist() == [event_id] * 7
        assert bool((horizon.history_time <= horizon.analysis_time).all())
        assert bool((horizon.target_time > horizon.analysis_time).all())
