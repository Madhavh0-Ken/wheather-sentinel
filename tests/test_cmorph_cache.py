import bz2
import gzip
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from storm_nowcast.config import Bounds
from storm_nowcast.data.download import DownloadResult
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.data.rainfall import CmorphGridSpec
from storm_nowcast.events.errors import EventErrorCode, EventOperationError


TINY_GRID = CmorphGridSpec(
    nx=4,
    ny=3,
    lon_start=75.0,
    lon_step=1.0,
    lat_start=29.0,
    lat_step=1.0,
)
BOUNDS = Bounds(min_lat=29.0, max_lat=31.0, min_lon=75.0, max_lon=77.0)
HOUR = datetime(2023, 7, 9, 6, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def _payload() -> bytes:
    return np.arange(24, dtype="<f4").reshape(2, 3, 4).tobytes()


def _write_archive(path: Path, payload: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else bz2.open
    with opener(path, "wb") as handle:
        handle.write(_payload() if payload is None else payload)


def _cache(tmp_path, downloader):
    from storm_nowcast.data.cmorph_cache import CmorphCache

    return CmorphCache(
        tmp_path,
        downloader=downloader,
        clock=lambda: NOW,
        grid_spec=TINY_GRID,
    )


def _destination(tmp_path: Path) -> Path:
    return tmp_path / "CMORPH_V0.x_RAW_8km-30min_2023070906.gz"


def test_valid_cache_is_reused_without_network_and_legacy_metadata_is_adopted(tmp_path):
    path = _destination(tmp_path)
    _write_archive(path)

    def forbidden_download(*args, **kwargs):
        raise AssertionError("network must not be used for a valid cached archive")

    asset = _cache(tmp_path, forbidden_download).get(HOUR, BOUNDS)

    assert asset.path == path
    assert asset.reused is True
    assert asset.downloaded is False
    assert asset.sha256 == sha256_file(path)
    assert "legacy cache" in asset.acquisition_evidence
    metadata = json.loads(path.with_suffix(".gz.meta.json").read_text(encoding="utf-8"))
    assert metadata["official_url"].endswith("2023070906.gz")
    assert metadata["sha256"] == asset.sha256
    assert "legacy cache" in metadata["acquisition_evidence"]


def test_concurrent_reuse_of_one_hour_serializes_shared_metadata_write(tmp_path, monkeypatch):
    from storm_nowcast.data.cmorph_cache import CmorphCache

    path = _destination(tmp_path)
    _write_archive(path)
    first_metadata_write = threading.Event()
    release_first = threading.Event()
    active_writers = 0
    overlap_observed = False
    writer_guard = threading.Lock()
    original_write_metadata = CmorphCache._write_metadata

    def controlled_write_metadata(self, *args, **kwargs):
        nonlocal active_writers, overlap_observed
        with writer_guard:
            active_writers += 1
            overlap_observed = overlap_observed or active_writers > 1
            current = active_writers
        if current == 1:
            first_metadata_write.set()
            release_first.wait(timeout=1)
        try:
            return original_write_metadata(self, *args, **kwargs)
        finally:
            with writer_guard:
                active_writers -= 1

    monkeypatch.setattr(CmorphCache, "_write_metadata", controlled_write_metadata)
    results = []
    errors = []

    def reuse():
        try:
            results.append(
                _cache(tmp_path, lambda *_args, **_kwargs: None).get(
                    HOUR, BOUNDS, allow_download=False
                )
            )
        except Exception as exc:  # the assertion below reports the real cross-thread failure
            errors.append(exc)

    first = threading.Thread(target=reuse)
    second = threading.Thread(target=reuse)
    first.start()
    assert first_metadata_write.wait(timeout=5)
    second.start()
    second.join(timeout=0.2)
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert overlap_observed is False
    assert not errors
    assert len(results) == 2
    assert all(asset.reused for asset in results)
    metadata = json.loads(path.with_suffix(".gz.meta.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == sha256_file(path)


def test_empty_requested_crop_does_not_invalidate_valid_shared_archive(tmp_path):
    from storm_nowcast.data.cmorph_cache import validate_cmorph_archive

    path = _destination(tmp_path)
    _write_archive(path)
    between_grid_centers = Bounds(
        min_lat=29.1,
        max_lat=29.2,
        min_lon=75.1,
        max_lon=75.2,
    )

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, lambda *_args, **_kwargs: None).get(
            HOUR,
            between_grid_centers,
            allow_download=False,
        )

    assert captured.value.code == EventErrorCode.INVALID_BOUNDS
    assert path.exists()
    assert validate_cmorph_archive(path, grid_spec=TINY_GRID) == len(_payload())


def test_metadata_promotion_failure_preserves_valid_archive_and_returns_storage_error(
    tmp_path, monkeypatch
):
    from storm_nowcast.data.cmorph_cache import CmorphCache, validate_cmorph_archive

    path = _destination(tmp_path)
    _write_archive(path)
    download_attempted = False

    def forbidden_download(*_args, **_kwargs):
        nonlocal download_attempted
        download_attempted = True
        raise AssertionError("metadata failure must not trigger a NOAA download")

    def fail_metadata_write(*_args, **_kwargs):
        raise PermissionError("simulated OneDrive sharing violation")

    monkeypatch.setattr(CmorphCache, "_write_metadata", fail_metadata_write)

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, forbidden_download).get(HOUR, BOUNDS)

    assert captured.value.code == EventErrorCode.EVENT_STORAGE_FAILED
    assert download_attempted is False
    assert path.exists()
    assert validate_cmorph_archive(path, grid_spec=TINY_GRID) == len(_payload())


@pytest.mark.parametrize("suffix", [".gz", ".bz2"])
def test_archive_validation_accepts_exact_gzip_and_bzip2_layout(tmp_path, suffix):
    from storm_nowcast.data.cmorph_cache import validate_cmorph_archive

    path = tmp_path / f"source{suffix}"
    _write_archive(path)

    assert validate_cmorph_archive(path, grid_spec=TINY_GRID) == len(_payload())


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [(b"short", "expected 96 bytes"), (None, "compressed")],
)
def test_invalid_cached_archive_is_rejected_offline(tmp_path, payload, expected_message):
    path = _destination(tmp_path)
    if payload is None:
        path.write_bytes(b"not-gzip")
    else:
        _write_archive(path, payload)

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, lambda *args, **kwargs: None).get(
            HOUR,
            BOUNDS,
            allow_download=False,
        )

    assert captured.value.code == EventErrorCode.NOAA_FILE_CORRUPT
    assert expected_message in captured.value.message.lower()


def test_mismatched_sidecar_is_not_reused_and_official_file_is_redownloaded(tmp_path):
    path = _destination(tmp_path)
    _write_archive(path)
    path.with_suffix(".gz.meta.json").write_text(
        json.dumps(
            {
                "official_url": "https://ftp.cpc.ncep.noaa.gov/wrong.gz",
                "sha256": sha256_file(path),
                "acquired_at": "2024-05-18T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    def downloader(url, destination, *, reuse_existing=True):
        assert reuse_existing is False
        _write_archive(destination)
        return DownloadResult(destination, sha256_file(destination), True, destination.stat().st_size)

    asset = _cache(tmp_path, downloader).get(HOUR, BOUNDS)

    assert asset.downloaded is True
    assert asset.reused is False
    metadata = json.loads(path.with_suffix(".gz.meta.json").read_text(encoding="utf-8"))
    assert metadata["official_url"] == asset.official_url


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("source_filename", "different-hour.gz"),
        ("compressed_byte_count", 1),
        ("acquired_at", "2024-05-18T00:00:00"),
    ],
)
def test_offline_sidecar_requires_matching_file_facts_and_aware_time(
    tmp_path, field, invalid_value
):
    path = _destination(tmp_path)
    _write_archive(path)
    metadata = {
        "official_url": "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_V0.x/RAW/8km-30min/2023/202307/CMORPH_V0.x_RAW_8km-30min_2023070906.gz",
        "source_filename": path.name,
        "compressed_byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
        "acquired_at": "2024-05-18T00:00:00Z",
    }
    metadata[field] = invalid_value
    path.with_suffix(".gz.meta.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, lambda *_args, **_kwargs: None).get(
            HOUR, BOUNDS, allow_download=False
        )

    assert captured.value.code == EventErrorCode.NOAA_FILE_CORRUPT
    assert path.exists()


def test_invalid_download_is_retried_once_then_succeeds(tmp_path):
    attempts = 0

    def downloader(url, destination, *, reuse_existing=True):
        nonlocal attempts
        attempts += 1
        _write_archive(destination, b"short" if attempts == 1 else _payload())
        return DownloadResult(destination, sha256_file(destination), True, destination.stat().st_size)

    asset = _cache(tmp_path, downloader).get(HOUR, BOUNDS)

    assert attempts == 2
    assert asset.downloaded is True
    assert asset.dataset.sizes == {"time": 2, "latitude": 3, "longitude": 3}


def test_new_download_records_the_injected_acquisition_time(tmp_path):
    def downloader(url, destination, *, reuse_existing=True):
        _write_archive(destination)
        return DownloadResult(destination, sha256_file(destination), True, destination.stat().st_size)

    asset = _cache(tmp_path, downloader).get(HOUR, BOUNDS)

    assert asset.acquired_at == NOW
    metadata = json.loads(asset.path.with_suffix(".gz.meta.json").read_text(encoding="utf-8"))
    assert metadata["acquired_at"] == "2026-09-26T12:00:00Z"
    assert metadata["acquisition_evidence"] == "downloaded from official NOAA CPC HTTPS archive"


def test_two_invalid_downloads_stop_with_corrupt_code(tmp_path):
    attempts = 0

    def downloader(url, destination, *, reuse_existing=True):
        nonlocal attempts
        attempts += 1
        _write_archive(destination, b"short")
        return DownloadResult(destination, sha256_file(destination), True, destination.stat().st_size)

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, downloader).get(HOUR, BOUNDS)

    assert attempts == 2
    assert captured.value.code == EventErrorCode.NOAA_FILE_CORRUPT


def test_network_failures_stop_after_two_attempts_with_unavailable_code(tmp_path):
    attempts = 0

    def downloader(url, destination, *, reuse_existing=True):
        nonlocal attempts
        attempts += 1
        raise OSError("NOAA connection unavailable")

    with pytest.raises(EventOperationError) as captured:
        _cache(tmp_path, downloader).get(HOUR, BOUNDS)

    assert attempts == 2
    assert captured.value.code == EventErrorCode.NOAA_UNAVAILABLE
    assert "2023070906" in captured.value.message
