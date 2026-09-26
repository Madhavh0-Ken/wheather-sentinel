from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from storm_nowcast.config import Bounds, load_settings
from storm_nowcast.data.cmorph_cache import CachedCmorphAsset
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.events.custom import CustomEventRequest, custom_event_id
from storm_nowcast.events.errors import EventOperationError
from tests.test_event_repository import _repository


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class TinyCache:
    def __init__(self, root: Path, *, rain: float = 12.0) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        self.rain = rain
        self.calls: list[tuple[datetime, Bounds, bool]] = []
        self.fail = False

    def get(self, hour, bounds, *, allow_download=True):
        if self.fail:
            raise RuntimeError("injected source failure")
        self.calls.append((hour, bounds, allow_download))
        path = self.root / f"{hour:%Y%m%d%H}.gz"
        path.write_bytes(f"official-{hour.isoformat()}".encode())
        times = np.array(
            [
                np.datetime64(hour.replace(tzinfo=None), "ns"),
                np.datetime64((hour + timedelta(minutes=30)).replace(tzinfo=None), "ns"),
            ]
        )
        rain = np.full((2, 3, 4), self.rain, dtype=np.float32)
        rain[:, 0, 0] = np.nan
        dataset = xr.Dataset(
            {
                "rain_rate": (("time", "latitude", "longitude"), rain),
                "missing_mask": (("time", "latitude", "longitude"), np.isnan(rain)),
            },
            coords={
                "time": times,
                "latitude": [30.0, 30.1, 30.2],
                "longitude": [75.0, 75.1, 75.2, 75.3],
            },
            attrs={
                "provider": "NOAA Climate Prediction Center",
                "product": "CMORPH V0.x RAW 8km-30min",
                "source_resolution": "~8 km grid spacing; effective source resolution is coarser",
                "crs": "EPSG:4326",
                "is_synthetic": False,
            },
        )
        return CachedCmorphAsset(
            path=path,
            official_url=f"https://ftp.cpc.ncep.noaa.gov/{path.name}",
            sha256=sha256_file(path),
            compressed_byte_count=path.stat().st_size,
            acquired_at=NOW,
            validated_at=NOW,
            downloaded=False,
            reused=True,
            dataset=dataset,
        )


def event_request(*, name: str = "Monsoon sector") -> CustomEventRequest:
    return CustomEventRequest(
        min_lat=30.0,
        max_lat=30.2,
        min_lon=75.0,
        max_lon=75.3,
        start_time=datetime(2023, 7, 9, 0, 30, tzinfo=timezone.utc),
        end_time=datetime(2023, 7, 9, 1, 30, tzinfo=timezone.utc),
        event_name=name,
    )


def make_builder(tmp_path: Path, *, rain: float = 12.0):
    from storm_nowcast.events.builder import CmorphEventBuilder

    repository, custom_root, _ = _repository(tmp_path)
    cache = TinyCache(tmp_path / "raw", rain=rain)
    builder = CmorphEventBuilder(
        repository,
        cache,
        load_settings(),
        clock=lambda: NOW,
    )
    return builder, repository, custom_root, cache


def test_builder_prepares_exact_inclusive_event_with_provenance_and_progress(tmp_path):
    from storm_nowcast.events.builder import BuildStage

    builder, repository, _, cache = make_builder(tmp_path)
    stages = []

    prepared = builder.prepare(event_request(), progress=stages.append, allow_download=False)

    assert prepared.created is True and prepared.reused is False
    assert prepared.manifest.event_id == custom_event_id(event_request())
    assert prepared.manifest.display_name == "Monsoon sector"
    assert prepared.manifest.expected_frame_count == prepared.manifest.frame_count == 3
    assert prepared.manifest.source_files[0]["reused"] is True
    assert [call[0].hour for call in cache.calls] == [0, 1]
    assert all(call[2] is False for call in cache.calls)
    with xr.open_dataset(prepared.record.data_path, engine="h5netcdf") as event:
        assert event.time.values.tolist() == np.array(
            ["2023-07-09T00:30", "2023-07-09T01:00", "2023-07-09T01:30"],
            dtype="datetime64[ns]",
        ).tolist()
        assert np.isnan(event.rain_rate.values[:, 0, 0]).all()
        assert event.missing_mask.values[:, 0, 0].all()
        assert event.attrs["event_id"] == prepared.manifest.event_id
    assert repository.validate_ready(prepared.manifest.event_id).event_sha256
    assert stages[0] == BuildStage.CHECKING_ARCHIVE
    assert stages[-1] == BuildStage.COMPLETE
    assert set(stages) >= set(BuildStage)


def test_builder_revalidates_and_reuses_same_identity_without_touching_source(tmp_path):
    builder, _, _, cache = make_builder(tmp_path)
    first = builder.prepare(event_request(name="First name"), allow_download=False)
    cache.fail = True

    reused = builder.prepare(event_request(name="Different display name"), allow_download=False)

    assert reused.created is False and reused.reused is True
    assert reused.manifest.event_id == first.manifest.event_id
    assert reused.manifest.display_name == "First name"


def test_dry_event_is_valid_and_qualified_without_cells(tmp_path):
    builder, repository, _, _ = make_builder(tmp_path, rain=0.0)

    prepared = builder.prepare(event_request(), allow_download=False)

    assert prepared.manifest.analysis_ready is True
    assert prepared.manifest.analysis_summary["detected_cell_count"] == 0
    assert prepared.manifest.analysis_summary["forecast_ready_track_count"] == 0
    assert repository.get(prepared.manifest.event_id).ready is True


@pytest.mark.parametrize("failure_point", ["source", "write", "verify", "promote"])
def test_builder_failure_always_cleans_temporary_directory_and_owned_lock(
    tmp_path, monkeypatch, failure_point
):
    import storm_nowcast.events.builder as builder_module

    builder, repository, custom_root, cache = make_builder(tmp_path)
    if failure_point == "source":
        cache.fail = True
    elif failure_point == "write":
        monkeypatch.setattr(builder_module, "save_event", lambda *_: (_ for _ in ()).throw(OSError("write")))
    elif failure_point == "verify":
        monkeypatch.setattr(repository, "validate_directory", lambda *_: (_ for _ in ()).throw(ValueError("verify")))
    else:
        monkeypatch.setattr(repository, "promote", lambda *_: (_ for _ in ()).throw(OSError("promote")))

    with pytest.raises(EventOperationError):
        builder.prepare(event_request(), allow_download=False)

    assert not list(custom_root.glob(".tmp-*"))
    assert not list((custom_root / ".locks").glob("*.lock"))
