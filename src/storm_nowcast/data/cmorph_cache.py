from __future__ import annotations

import bz2
import gzip
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import xarray as xr

from storm_nowcast.config import Bounds
from storm_nowcast.data.download import DownloadResult, download_file
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.data.rainfall import (
    CMORPH_GRID,
    CmorphCropError,
    CmorphGridSpec,
    load_cmorph_file,
)
from storm_nowcast.data.sources import CmorphSource
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.events.locking import EventBuildLock


Downloader = Callable[..., DownloadResult]
CACHE_LOCK_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class CachedCmorphAsset:
    path: Path
    official_url: str
    sha256: str
    compressed_byte_count: int
    acquired_at: datetime
    validated_at: datetime
    downloaded: bool
    reused: bool
    dataset: xr.Dataset
    acquisition_evidence: str = "cache metadata"


def validate_cmorph_archive(
    path: Path,
    *,
    grid_spec: CmorphGridSpec = CMORPH_GRID,
) -> int:
    path = Path(path)
    try:
        if path.suffix.lower() == ".gz":
            with gzip.open(path, "rb") as handle:
                payload = handle.read()
        elif path.suffix.lower() == ".bz2":
            with bz2.open(path, "rb") as handle:
                payload = handle.read()
        else:
            raise ValueError(f"Unsupported CMORPH compression suffix: {path.suffix}")
    except (OSError, EOFError) as exc:
        raise ValueError("Compressed CMORPH archive could not be read") from exc
    expected = 2 * grid_spec.ny * grid_spec.nx * 4
    if len(payload) != expected:
        raise ValueError(
            f"Invalid CMORPH payload: expected {expected} bytes, got {len(payload)}"
        )
    return len(payload)


class CmorphCache:
    def __init__(
        self,
        root: Path,
        *,
        downloader: Downloader = download_file,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        grid_spec: CmorphGridSpec = CMORPH_GRID,
    ) -> None:
        self.root = Path(root)
        self.downloader = downloader
        self.clock = clock
        self.grid_spec = grid_spec
        self.source = CmorphSource()

    @staticmethod
    def _metadata_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".meta.json")

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Cached CMORPH acquisition time must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    def _write_metadata(
        self,
        path: Path,
        *,
        official_url: str,
        checksum: str,
        acquired_at: datetime,
        validated_at: datetime,
        acquisition_evidence: str,
    ) -> None:
        metadata_path = self._metadata_path(path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "official_url": official_url,
            "source_filename": path.name,
            "compressed_byte_count": path.stat().st_size,
            "sha256": checksum,
            "acquired_at": acquired_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "validated_at": validated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "acquisition_evidence": acquisition_evidence,
        }
        temporary = metadata_path.with_name(
            f".{metadata_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(metadata_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _validated_asset(
        self,
        path: Path,
        *,
        hour: datetime,
        bounds: Bounds,
        official_url: str,
        downloaded: bool,
    ) -> CachedCmorphAsset:
        validate_cmorph_archive(path, grid_spec=self.grid_spec)
        checksum = sha256_file(path)
        validated_at = self.clock().astimezone(timezone.utc)
        metadata_path = self._metadata_path(path)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("official_url") != official_url:
                raise ValueError("Cached CMORPH metadata official URL does not match")
            if metadata.get("source_filename") != path.name:
                raise ValueError("Cached CMORPH metadata source filename does not match")
            if metadata.get("compressed_byte_count") != path.stat().st_size:
                raise ValueError("Cached CMORPH metadata byte count does not match")
            if metadata.get("sha256") != checksum:
                raise ValueError("Cached CMORPH checksum does not match metadata")
            acquired_at = self._parse_time(metadata["acquired_at"])
            acquisition_evidence = str(metadata.get("acquisition_evidence", "cache metadata"))
        else:
            if downloaded:
                acquired_at = validated_at
                acquisition_evidence = "downloaded from official NOAA CPC HTTPS archive"
            else:
                acquired_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                acquisition_evidence = "legacy cache file timestamp adopted after full validation"
        try:
            dataset = load_cmorph_file(path, hour, bounds, grid_spec=self.grid_spec)
        except CmorphCropError as exc:
            raise EventOperationError(
                EventErrorCode.INVALID_BOUNDS,
                "The requested region does not contain a native CMORPH grid cell.",
                details={
                    "min_lat": bounds.min_lat,
                    "max_lat": bounds.max_lat,
                    "min_lon": bounds.min_lon,
                    "max_lon": bounds.max_lon,
                },
            ) from exc
        try:
            self._write_metadata(
                path,
                official_url=official_url,
                checksum=checksum,
                acquired_at=acquired_at,
                validated_at=validated_at,
                acquisition_evidence=acquisition_evidence,
            )
        except OSError as exc:
            raise EventOperationError(
                EventErrorCode.EVENT_STORAGE_FAILED,
                "CMORPH cache metadata could not be stored safely.",
                details={"path": str(self._metadata_path(path)), "official_url": official_url},
            ) from exc
        return CachedCmorphAsset(
            path=path,
            official_url=official_url,
            sha256=checksum,
            compressed_byte_count=path.stat().st_size,
            acquired_at=acquired_at,
            validated_at=validated_at,
            downloaded=downloaded,
            reused=not downloaded,
            dataset=dataset,
            acquisition_evidence=acquisition_evidence,
        )

    def _remove_invalid_entry(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        self._metadata_path(path).unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".part").unlink(missing_ok=True)

    def get(
        self,
        hour: datetime,
        bounds: Bounds,
        *,
        allow_download: bool = True,
    ) -> CachedCmorphAsset:
        official_url = self.source.build_url(hour)
        path = self.root / Path(official_url).name
        lock_id = f"cmorph-cache-{hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:16]}"
        lock = EventBuildLock(self.root / ".locks", lock_id)
        deadline = time.monotonic() + CACHE_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                lock.acquire()
                break
            except EventOperationError as exc:
                if (
                    exc.code != EventErrorCode.EVENT_BUILD_IN_PROGRESS
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.05)
        try:
            return self._get_locked(
                hour,
                bounds,
                official_url=official_url,
                path=path,
                allow_download=allow_download,
            )
        finally:
            lock.release()

    def _get_locked(
        self,
        hour: datetime,
        bounds: Bounds,
        *,
        official_url: str,
        path: Path,
        allow_download: bool,
    ) -> CachedCmorphAsset:
        cached_error: Exception | None = None
        if path.exists():
            try:
                return self._validated_asset(
                    path,
                    hour=hour,
                    bounds=bounds,
                    official_url=official_url,
                    downloaded=False,
                )
            except EventOperationError:
                raise
            except Exception as exc:
                cached_error = exc
                if not allow_download:
                    raise EventOperationError(
                        EventErrorCode.NOAA_FILE_CORRUPT,
                        f"Cached CMORPH file is invalid: {exc}",
                        details={"path": str(path), "official_url": official_url},
                    ) from exc
                self._remove_invalid_entry(path)
        elif not allow_download:
            raise EventOperationError(
                EventErrorCode.NOAA_UNAVAILABLE,
                f"Required cached CMORPH file is unavailable: {path.name}",
                details={"official_url": official_url},
            )

        last_download_error: Exception | None = None
        last_validation_error: Exception | None = cached_error
        for _ in range(2):
            try:
                self.downloader(official_url, path, reuse_existing=False)
            except Exception as exc:
                last_download_error = exc
                continue
            try:
                return self._validated_asset(
                    path,
                    hour=hour,
                    bounds=bounds,
                    official_url=official_url,
                    downloaded=True,
                )
            except EventOperationError:
                raise
            except Exception as exc:
                last_validation_error = exc
                self._remove_invalid_entry(path)

        if last_validation_error is not None:
            raise EventOperationError(
                EventErrorCode.NOAA_FILE_CORRUPT,
                f"CMORPH file {path.name} failed bounded validation: {last_validation_error}",
                details={"official_url": official_url},
            ) from last_validation_error
        raise EventOperationError(
            EventErrorCode.NOAA_UNAVAILABLE,
            f"Official NOAA CMORPH file {path.name} is unavailable after two attempts.",
            details={"official_url": official_url, "reason": str(last_download_error)},
        ) from last_download_error
