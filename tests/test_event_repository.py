import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from storm_nowcast.config import Bounds
from storm_nowcast.data.provenance import sha256_file, write_manifest
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.models.schemas import ProvenanceRecord
from storm_nowcast.replay.player import save_event
from tests.test_replay import replay_dataset


EVENT_ID = "cmorph-custom-20230709T0000Z-30p10N-75p15E-a1b2c3d4"
START = datetime(2023, 7, 9, 0, 0, tzinfo=timezone.utc)
END = datetime(2023, 7, 9, 1, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _builtin_catalog(tmp_path: Path) -> tuple[Path, Path]:
    event_path = tmp_path / "builtin.nc"
    event_path.write_bytes(b"immutable built-in")
    catalog = tmp_path / "configs" / "events.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        yaml.safe_dump(
            {
                "events": [
                    {
                        "id": "builtin-event",
                        "name": "Built-in event",
                        "region": "Reference region",
                        "observation_start": "2023-07-09T00:00:00Z",
                        "observation_end": "2023-07-09T01:00:00Z",
                        "sources": ["NOAA CPC CMORPH"],
                        "frame_count": 3,
                        "data_path": str(event_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return catalog, event_path


def _write_custom_event(directory: Path, event_id: str = EVENT_ID):
    from storm_nowcast.events.custom import CustomEventManifest

    directory.mkdir(parents=True)
    dataset = replay_dataset().copy(deep=True)
    dataset.attrs["event_id"] = event_id
    dataset.attrs["observation_start"] = "2023-07-09T00:00:00Z"
    dataset.attrs["observation_end"] = "2023-07-09T01:00:00Z"
    event_path = directory / "event.nc"
    save_event(dataset, event_path)
    provenance_path = directory / "provenance.json"
    source = directory / "official.gz"
    source.write_bytes(b"official fixture")
    write_manifest(
        provenance_path,
        [
            ProvenanceRecord(
                provider="NOAA Climate Prediction Center",
                product="CMORPH V0.x RAW 8km-30min",
                source_url="https://ftp.cpc.ncep.noaa.gov/official.gz",
                acquired_at=NOW,
                observation_start=START,
                observation_end=START + timedelta(minutes=30),
                sha256=sha256_file(source),
                local_file=str(source),
                processing_steps=["synthetic structural fixture"],
                is_synthetic=True,
            )
        ],
    )
    manifest = CustomEventManifest(
        event_id=event_id,
        display_name="Custom reference event",
        bounding_box=Bounds(min_lat=30.0, max_lat=30.2, min_lon=75.0, max_lon=75.3),
        start_time=START,
        end_time=END,
        expected_frame_count=3,
        frame_count=3,
        provider="NOAA Climate Prediction Center",
        source_product="CMORPH V0.x RAW 8km-30min",
        native_resolution="~8 km grid spacing; effective source resolution is coarser",
        created_at=NOW,
        event_sha256=sha256_file(event_path),
        provenance_sha256=sha256_file(provenance_path),
        stored_bytes=event_path.stat().st_size + provenance_path.stat().st_size,
        analysis_ready=True,
        analysis_summary={"detected_cell_count": 1},
    )
    (directory / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest


def _repository(tmp_path: Path):
    from storm_nowcast.events.repository import EventRepository

    catalog, builtin_path = _builtin_catalog(tmp_path)
    custom_root = tmp_path / "data" / "events" / "custom"
    return EventRepository(catalog, custom_root), custom_root, builtin_path


def test_repository_merges_immutable_builtin_and_validated_custom_events(tmp_path):
    repository, custom_root, _ = _repository(tmp_path)
    _write_custom_event(custom_root / EVENT_ID)

    events = repository.list_events()

    assert [(item.kind, item.event_id) for item in events] == [
        ("builtin", "builtin-event"),
        ("custom", EVENT_ID),
    ]
    custom = repository.get(EVENT_ID)
    assert custom.ready is True
    assert custom.data_path == custom_root / EVENT_ID / "event.nc"
    assert repository.validate_ready(EVENT_ID).schema_version == 1


@pytest.mark.parametrize("failure", ["schema", "missing", "checksum", "provenance"])
def test_cached_event_readiness_rejects_invalid_schema_files_and_checksums(tmp_path, failure):
    repository, custom_root, _ = _repository(tmp_path)
    directory = custom_root / EVENT_ID
    _write_custom_event(directory)
    if failure == "schema":
        body = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        body["schema_version"] = 99
        (directory / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
    elif failure == "missing":
        (directory / "event.nc").unlink()
    elif failure == "checksum":
        with (directory / "event.nc").open("ab") as handle:
            handle.write(b"tampered")
    else:
        (directory / "provenance.json").write_text("{}", encoding="utf-8")

    with pytest.raises(EventOperationError) as captured:
        repository.validate_ready(EVENT_ID)

    assert captured.value.code == EventErrorCode.CACHED_EVENT_INVALID


def test_current_lock_is_exclusive_and_only_owner_can_release(tmp_path):
    from storm_nowcast.events.locking import EventBuildLock

    first = EventBuildLock(tmp_path, EVENT_ID, clock=lambda: NOW, owner_token="first")
    second = EventBuildLock(tmp_path, EVENT_ID, clock=lambda: NOW, owner_token="second")
    first.acquire()

    with pytest.raises(EventOperationError) as captured:
        second.acquire()
    assert captured.value.code == EventErrorCode.EVENT_BUILD_IN_PROGRESS
    second.release()
    assert first.path.exists()
    first.release()
    assert not first.path.exists()


def test_stale_lock_recovery_has_one_new_owner_and_old_owner_cannot_release_it(tmp_path):
    from storm_nowcast.events.locking import EventBuildLock

    old = EventBuildLock(tmp_path, EVENT_ID, clock=lambda: NOW, owner_token="old")
    old.acquire()
    later = NOW + timedelta(hours=3)
    winner = EventBuildLock(tmp_path, EVENT_ID, clock=lambda: later, owner_token="winner")
    loser = EventBuildLock(tmp_path, EVENT_ID, clock=lambda: later, owner_token="loser")

    winner.acquire()
    with pytest.raises(EventOperationError):
        loser.acquire()
    old.release()
    assert winner.path.exists()
    assert json.loads(winner.path.read_text(encoding="utf-8"))["owner_token"] == "winner"
    winner.release()


def test_verified_temporary_directory_is_promoted_once_without_overwrite(tmp_path):
    repository, custom_root, _ = _repository(tmp_path)
    temporary = custom_root / f".tmp-{EVENT_ID}-one"
    _write_custom_event(temporary)

    final = repository.promote(temporary, EVENT_ID)

    assert final == custom_root / EVENT_ID
    assert final.is_dir()
    assert not temporary.exists()
    second = custom_root / f".tmp-{EVENT_ID}-two"
    _write_custom_event(second)
    with pytest.raises(EventOperationError) as captured:
        repository.promote(second, EVENT_ID)
    assert captured.value.code == EventErrorCode.CACHED_EVENT_INVALID
    assert second.exists()


def test_deletion_accepts_only_valid_custom_ids_and_preserves_builtin_and_raw_cache(tmp_path):
    repository, custom_root, builtin_path = _repository(tmp_path)
    _write_custom_event(custom_root / EVENT_ID)
    raw_file = tmp_path / "data" / "raw" / "cmorph" / "shared.gz"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"shared official cache")

    with pytest.raises(EventOperationError) as protected:
        repository.delete("builtin-event")
    assert protected.value.code == EventErrorCode.BUILTIN_EVENT_PROTECTED
    with pytest.raises(EventOperationError) as missing:
        repository.delete("cmorph-custom-unknown")
    assert missing.value.code == EventErrorCode.EVENT_NOT_FOUND
    with pytest.raises(EventOperationError) as unsafe:
        repository.delete("../builtin-event")
    assert unsafe.value.code == EventErrorCode.UNSAFE_EVENT_PATH

    repository.delete(EVENT_ID)

    assert not (custom_root / EVENT_ID).exists()
    assert builtin_path.exists()
    assert raw_file.read_bytes() == b"shared official cache"


def test_deletion_rejects_manifest_identity_mismatch(tmp_path):
    repository, custom_root, _ = _repository(tmp_path)
    directory = custom_root / EVENT_ID
    _write_custom_event(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["event_id"] = "cmorph-custom-forged"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EventOperationError) as captured:
        repository.delete(EVENT_ID)

    assert captured.value.code == EventErrorCode.UNSAFE_EVENT_PATH
    assert directory.exists()


def test_deletion_rejects_symlinked_custom_directory_when_supported(tmp_path):
    repository, custom_root, _ = _repository(tmp_path)
    outside = tmp_path / "outside"
    _write_custom_event(outside, event_id=EVENT_ID)
    custom_root.mkdir(parents=True, exist_ok=True)
    link = custom_root / EVENT_ID
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks require elevated privileges on this Windows host")

    with pytest.raises(EventOperationError) as captured:
        repository.delete(EVENT_ID)

    assert captured.value.code == EventErrorCode.UNSAFE_EVENT_PATH
    assert outside.exists()
