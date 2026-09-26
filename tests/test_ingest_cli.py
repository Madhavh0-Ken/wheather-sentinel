import json
import subprocess
import sys

import pytest
import xarray as xr

from scripts.ingest_official import parse_assignments
from tests.test_insat3dr_l1c import _write_l1c_fixture


def test_cli_assignment_parser_requires_explicit_unique_name_pairs():
    assert parse_assignments(["rain_rate=RR", "radar_reflectivity=DBZ"]) == {
        "rain_rate": "RR",
        "radar_reflectivity": "DBZ",
    }

    with pytest.raises(ValueError, match="NAME=SOURCE_NAME"):
        parse_assignments(["ambiguous"])
    with pytest.raises(ValueError, match="Duplicate"):
        parse_assignments(["rain_rate=A", "rain_rate=B"])


def test_cli_ingests_documented_insat3dr_l1c_without_guessed_mapping_or_resolution(tmp_path):
    source = tmp_path / "3RIMG_09JUL2023_0000_L1C_ASIA_MER_V01R00.h5"
    output = tmp_path / "insat-normalized.nc"
    _write_l1c_fixture(source, include_wv=True)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/ingest_official.py",
            "--source",
            "mosdac-insat3dr-l1c",
            "--input",
            str(source),
            "--output",
            str(output),
            "--min-lat",
            "29",
            "--max-lat",
            "33",
            "--min-lon",
            "74",
            "--max-lon",
            "78",
            "--confirm-official-origin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Imported mosdac-insat3dr-l1c asset" in result.stdout
    with xr.open_dataset(output, engine="h5netcdf") as normalized:
        assert set(normalized.data_vars) == {
            "infrared_brightness_temperature",
            "water_vapour_brightness_temperature",
        }
        assert normalized.infrared_brightness_temperature.attrs["units"] == "K"
    metadata = json.loads(output.with_suffix(".nc.provenance.json").read_text(encoding="utf-8"))
    assert metadata["asset"]["source"]["product"] == "3RIMG_L1C_ASIA_MER"
    assert metadata["temporal_support"]["native_resolution_minutes"] == 30.0
