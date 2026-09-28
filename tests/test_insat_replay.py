from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import xarray as xr


EVENT_START = datetime(2023, 7, 9, 0, 0, tzinfo=timezone.utc)
EVENT_END = datetime(2023, 7, 9, 5, 30, tzinfo=timezone.utc)
EVENT_FILENAMES = (
    "3RIMG_08JUL2023_2345_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0015_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0045_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0115_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0145_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0215_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0245_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0315_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0345_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0415_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0445_L1C_ASIA_MER_V01R00.nc",
    "3RIMG_09JUL2023_0515_L1C_ASIA_MER_V01R00.nc",
)
EVENT_SOURCE_TIMES = tuple(
    datetime(2023, 7, 8, 23, 45, tzinfo=timezone.utc) + timedelta(minutes=30 * index)
    for index in range(12)
)
EVENT_TARGET_TIMES = tuple(
    np.datetime64("2023-07-09T00:00:00", "ns") + np.timedelta64(30 * index, "m")
    for index in range(12)
)


def _write_processed_insat(
    directory: Path,
    *,
    filename: str,
    observation_time: datetime,
    value: float = 235.0,
    provider: str = "ISRO/SAC MOSDAC",
    provenance_provider: str | None = None,
    all_missing: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    values = np.full((1, 2, 2), np.nan if all_missing else value, dtype=np.float64)
    dataset = xr.Dataset(
        {
            "infrared_brightness_temperature": (
                ("time", "latitude", "longitude"),
                values,
            ),
            "water_vapour_brightness_temperature": (
                ("time", "latitude", "longitude"),
                values + 5.0,
            ),
        },
        coords={
            "time": [np.datetime64(observation_time.replace(tzinfo=None), "ns")],
            "latitude": [30.0, 31.0],
            "longitude": [76.0, 77.0],
        },
        attrs={
            "provider": provider,
            "product": "3RIMG_L1C_ASIA_MER",
            "source_sha256": f"{int(value):064x}"[-64:],
            "is_synthetic": 1,
            "crs": "EPSG:4326",
            "native_crs": "MOSDAC file-supplied Mercator",
            "product_creation_time": (observation_time + timedelta(hours=6)).isoformat(),
            "format_contract": "MOSDAC INSAT-3D Data Products Format Document v1.1",
        },
    )
    for variable, source, lookup in (
        ("infrared_brightness_temperature", "IMG_TIR1", "IMG_TIR1_TEMP"),
        ("water_vapour_brightness_temperature", "IMG_WV", "IMG_WV_TEMP"),
    ):
        dataset[variable].attrs.update(
            {
                "units": "K",
                "provider": provider,
                "product": "3RIMG_L1C_ASIA_MER",
                "source_variable": source,
                "calibration_lookup_table": lookup,
                "variable_status": "OBSERVED",
                "native_resolution": json.dumps(
                    {
                        "grid_spacing_km": 4.0,
                        "native_description": f"{source} native L1C channel grid",
                        "effective_resolution_note": None,
                        "crs": "MOSDAC file-supplied Mercator",
                    }
                ),
            }
        )
    dataset.to_netcdf(path, engine="h5netcdf")

    sha256 = dataset.attrs["source_sha256"]
    lineage = {}
    for variable, source, lookup in (
        ("infrared_brightness_temperature", "IMG_TIR1", "IMG_TIR1_TEMP"),
        ("water_vapour_brightness_temperature", "IMG_WV", "IMG_WV_TEMP"),
    ):
        lineage[variable] = {
            "variable": variable,
            "source_record_ids": [f"sha256:{sha256}"],
            "status": "OBSERVED",
            "native_units": "digital count",
            "processed_units": "K",
            "native_spatial_resolution": {
                "grid_spacing_km": 4.0,
                "native_description": f"{source} native L1C channel grid",
                "effective_resolution_note": None,
                "crs": "MOSDAC file-supplied Mercator",
            },
            "analysis_grid_resolution_km": None,
            "resampling_method": "none",
            "native_temporal_resolution_minutes": 30.0,
            "processing_steps": [
                f"decoded {source} digital counts from user-supplied official HDF",
                f"applied file-supplied {lookup} brightness-temperature lookup table",
                "transformed file-supplied Mercator coordinates to EPSG:4326",
                "subset to configured bounds",
            ],
        }
    provenance = {
        "asset": {
            "path": str(Path("data/manual/mosdac_satellite") / path.with_suffix(".h5").name),
            "sha256": sha256,
            "size_bytes": 24_000_000,
            "source": {
                "provider": provenance_provider or provider,
                "product": "3RIMG_L1C_ASIA_MER",
                "sensor": "SATELLITE",
                "official_url": "https://mosdac.gov.in/doi/164/",
                "access_method": "registered MOSDAC user order; authenticated manual import",
                "authentication_required": True,
            },
            "acquired_at": "2026-09-28T06:53:00Z",
            "is_synthetic": True,
        },
        "lineage": lineage,
        "temporal_support": {
            "observation_start": (observation_time + timedelta(seconds=28)).isoformat(),
            "observation_end": (observation_time + timedelta(minutes=27)).isoformat(),
            "native_resolution_minutes": 30.0,
            "availability_time": (observation_time + timedelta(hours=6)).isoformat(),
        },
    }
    path.with_suffix(path.suffix + ".provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    return path


def _loaders():
    from storm_nowcast.data.insat_replay import (
        build_insat_replay_cube,
        load_processed_insat_observations,
    )

    return load_processed_insat_observations, build_insat_replay_cube


def test_processed_insat_loader_preserves_real_product_channels_and_provenance(tmp_path):
    path = _write_processed_insat(
        tmp_path,
        filename=EVENT_FILENAMES[0],
        observation_time=EVENT_SOURCE_TIMES[0],
    )

    load_observations, _ = _loaders()
    products = load_observations(
        tmp_path,
        event_start=EVENT_START,
        event_end=EVENT_END,
    )

    assert len(products) == 1
    product = products[0]
    assert product.asset.source.provider == "ISRO/SAC MOSDAC"
    assert product.asset.source.product == "3RIMG_L1C_ASIA_MER"
    assert product.asset.sha256 == product.dataset.attrs["source_sha256"]
    assert set(product.lineage) == {
        "infrared_brightness_temperature",
        "water_vapour_brightness_temperature",
    }
    assert product.lineage["infrared_brightness_temperature"].processed_units == "K"
    assert product.lineage["infrared_brightness_temperature"].native_spatial_resolution.grid_spacing_km == 4.0
    assert product.dataset.processed_source_file.item() == path.name


def test_real_event_uses_all_twelve_expected_causal_mappings_at_fifteen_minutes(tmp_path):
    for index, (filename, source_time) in enumerate(zip(EVENT_FILENAMES, EVENT_SOURCE_TIMES)):
        _write_processed_insat(
            tmp_path,
            filename=filename,
            observation_time=source_time,
            value=230.0 + index,
        )
    excluded = "3RIMG_09JUL2023_2345_L1C_ASIA_MER_V01R00.nc"
    _write_processed_insat(
        tmp_path,
        filename=excluded,
        observation_time=datetime(2023, 7, 9, 23, 45, tzinfo=timezone.utc),
        value=280.0,
    )

    _, build_cube = _loaders()
    cube = build_cube(
        tmp_path,
        target_times=EVENT_TARGET_TIMES,
        event_start=EVENT_START,
        event_end=EVENT_END,
    )

    assert cube is not None
    selected = cube["infrared_brightness_temperature__observation_time"].values
    expected = np.asarray(
        [np.datetime64(value.replace(tzinfo=None), "ns") for value in EVENT_SOURCE_TIMES]
    )
    assert np.array_equal(selected, expected)
    assert cube["infrared_brightness_temperature__age_minutes"].values.tolist() == [15.0] * 12
    assert cube["infrared_brightness_temperature__source_file"].values.tolist() == list(
        EVENT_FILENAMES
    )
    assert excluded not in cube["infrared_brightness_temperature__source_file"].values
    assert cube["infrared_brightness_temperature__available"].values.tolist() == [True] * 12


def test_causal_alignment_never_selects_a_future_observation(tmp_path):
    _write_processed_insat(
        tmp_path,
        filename=EVENT_FILENAMES[1],
        observation_time=datetime(2023, 7, 9, 0, 15, tzinfo=timezone.utc),
    )

    _, build_cube = _loaders()
    cube = build_cube(
        tmp_path,
        target_times=(np.datetime64("2023-07-09T00:00:00", "ns"),),
        event_start=EVENT_START,
        event_end=EVENT_END,
    )

    assert cube is not None
    assert cube.infrared_brightness_temperature__available.values.tolist() == [False]
    assert np.isnat(cube.infrared_brightness_temperature__observation_time.values[0])
    assert cube.infrared_brightness_temperature__missing.values.all()


def test_causal_alignment_accepts_exact_maximum_age_and_rejects_older_scan(tmp_path):
    _write_processed_insat(
        tmp_path,
        filename="scan.nc",
        observation_time=datetime(2023, 7, 9, 0, 0, tzinfo=timezone.utc),
    )

    _, build_cube = _loaders()
    cube = build_cube(
        tmp_path,
        target_times=(
            np.datetime64("2023-07-09T00:30:00.000000000", "ns"),
            np.datetime64("2023-07-09T00:30:00.000000001", "ns"),
        ),
        event_start=EVENT_START,
        event_end=EVENT_END,
        max_age_minutes=30,
    )

    assert cube is not None
    assert cube.infrared_brightness_temperature__available.values.tolist() == [True, False]
    assert cube.infrared_brightness_temperature__age_minutes.values[0] == 30.0
    assert np.isnan(cube.infrared_brightness_temperature__age_minutes.values[1])


def test_partial_and_missing_insat_coverage_produce_explicit_masks(tmp_path):
    _, build_cube = _loaders()
    missing = build_cube(
        tmp_path / "does-not-exist",
        target_times=EVENT_TARGET_TIMES[:2],
        event_start=EVENT_START,
        event_end=EVENT_END,
    )
    assert missing is None

    _write_processed_insat(
        tmp_path,
        filename=EVENT_FILENAMES[0],
        observation_time=EVENT_SOURCE_TIMES[0],
        value=240.0,
    )
    partial = build_cube(
        tmp_path,
        target_times=EVENT_TARGET_TIMES[:2],
        event_start=EVENT_START,
        event_end=EVENT_END,
    )

    assert partial is not None
    assert partial.infrared_brightness_temperature__available.values.tolist() == [True, False]
    assert not partial.infrared_brightness_temperature__missing.isel(time=0).values.any()
    assert partial.infrared_brightness_temperature__missing.isel(time=1).values.all()


def test_processed_insat_loader_rejects_duplicate_observation_times(tmp_path):
    for filename in ("duplicate-a.nc", "duplicate-b.nc"):
        _write_processed_insat(
            tmp_path,
            filename=filename,
            observation_time=EVENT_SOURCE_TIMES[0],
        )

    load_observations, _ = _loaders()
    with pytest.raises(ValueError, match="Duplicate INSAT observation time"):
        load_observations(tmp_path, event_start=EVENT_START, event_end=EVENT_END)


def test_processed_insat_loader_rejects_dataset_provenance_conflict(tmp_path):
    _write_processed_insat(
        tmp_path,
        filename="conflict.nc",
        observation_time=EVENT_SOURCE_TIMES[0],
        provider="ISRO/SAC MOSDAC",
        provenance_provider="UNRELATED PROVIDER",
    )

    load_observations, _ = _loaders()
    with pytest.raises(ValueError, match="provider"):
        load_observations(tmp_path, event_start=EVENT_START, event_end=EVENT_END)

