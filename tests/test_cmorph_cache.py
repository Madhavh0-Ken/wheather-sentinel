import bz2
import gzip
import json
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
    metadata = json.loads(path.with_suffix(".gz.meta.json").read_text(encoding="utf-8"))
    assert metadata["official_url"].endswith("2023070906.gz")
    assert metadata["sha256"] == asset.sha256
    assert "legacy cache" in metadata["acquisition_evidence"]


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
