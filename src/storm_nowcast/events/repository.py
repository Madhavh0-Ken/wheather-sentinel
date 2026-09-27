from __future__ import annotations

import json
import re
import shutil
from datetime import timedelta
from pathlib import Path

import numpy as np
import xarray as xr
from pydantic import ValidationError

from storm_nowcast.data.provenance import read_manifest, sha256_file
from storm_nowcast.events.catalog import load_event_catalog
from storm_nowcast.events.custom import (
    CMORPH_MAX_LAT,
    CMORPH_MIN_LAT,
    MAX_REGION_DEGREES,
    MAX_WINDOW,
    CustomEventManifest,
    EventLibraryRecord,
)
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.events.locking import _is_link_or_reparse_point
from storm_nowcast.preprocessing.validation import validate_weather_dataset


SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def _cached_invalid(message: str, **details: object) -> EventOperationError:
    return EventOperationError(EventErrorCode.CACHED_EVENT_INVALID, message, details=details)
class EventRepository:
    """The single path-safety and integrity boundary for event storage."""

    def __init__(self, builtin_catalog_path: Path, custom_root: Path) -> None:
        self.builtin_catalog_path = Path(builtin_catalog_path)
        self.custom_root = Path(custom_root).resolve()

    def _catalog(self):
        return load_event_catalog(self.builtin_catalog_path)

    @staticmethod
    def _require_safe_id(event_id: str) -> None:
        if not SAFE_EVENT_ID.fullmatch(event_id):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "Event IDs may contain only letters, numbers, and hyphens.",
                details={"event_id": event_id},
            )

    def _custom_path(self, event_id: str) -> Path:
        self._require_safe_id(event_id)
        return self.custom_root / event_id

    @staticmethod
    def _custom_record(directory: Path, manifest: CustomEventManifest) -> EventLibraryRecord:
        return EventLibraryRecord(
            event_id=manifest.event_id,
            display_name=manifest.display_name,
            kind="custom",
            data_path=directory / manifest.event_file,
            manifest_path=directory / "manifest.json",
            ready=True,
            start_time=manifest.start_time,
            end_time=manifest.end_time,
            frame_count=manifest.frame_count,
            stored_bytes=manifest.stored_bytes,
            bounding_box=manifest.bounding_box,
            analysis_ready=manifest.analysis_ready,
        )

    @staticmethod
    def _builtin_record(item) -> EventLibraryRecord:
        return EventLibraryRecord(
            event_id=item.id,
            display_name=item.name,
            kind="builtin",
            data_path=item.data_path,
            ready=item.data_path.is_file(),
            start_time=item.observation_start,
            end_time=item.observation_end,
            frame_count=item.frame_count,
            stored_bytes=item.data_path.stat().st_size if item.data_path.is_file() else 0,
        )

    def list_events(self) -> list[EventLibraryRecord]:
        catalog_events = self._catalog().events
        builtin_ids = {item.id for item in catalog_events}
        records = [self._builtin_record(item) for item in catalog_events]
        if self.custom_root.is_dir():
            for directory in sorted(self.custom_root.iterdir(), key=lambda value: value.name):
                if (
                    directory.name.startswith(".")
                    or directory.name in builtin_ids
                    or _is_link_or_reparse_point(directory)
                    or not directory.is_dir()
                ):
                    continue
                try:
                    manifest = self.validate_ready(directory.name)
                except EventOperationError:
                    continue
                records.append(self._custom_record(directory, manifest))
        return records

    def get(self, event_id: str) -> EventLibraryRecord:
        for item in self._catalog().events:
            if item.id == event_id:
                return self._builtin_record(item)
        directory = self._custom_path(event_id)
        if not directory.exists():
            raise EventOperationError(
                EventErrorCode.EVENT_NOT_FOUND,
                "The requested event does not exist.",
                details={"event_id": event_id},
            )
        return self._custom_record(directory, self.validate_ready(event_id))

    def _require_owned_directory(self, directory: Path, *, allow_temporary: bool) -> Path:
        candidate = Path(directory)
        if _is_link_or_reparse_point(candidate):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "Symlinked or reparse-point event directories are not allowed.",
            )
        try:
            parent = candidate.parent.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise _cached_invalid("The event directory is unavailable.", path=str(candidate)) from exc
        expected = self.custom_root / candidate.name
        if parent != self.custom_root or resolved != expected:
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "The event directory is outside custom event storage.")
        if not allow_temporary and candidate.name.startswith("."):
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "Temporary event directories are not repository events.")
        return candidate

    @staticmethod
    def _safe_member(directory: Path, filename: str) -> Path:
        if Path(filename).name != filename or filename in {"", ".", ".."}:
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "Manifest file names must be plain file names.")
        member = directory / filename
        if _is_link_or_reparse_point(member):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "Symlinked or reparse-point event files are not allowed.",
            )
        return member

    def _read_manifest_envelope(self, directory: Path) -> CustomEventManifest:
        path = self._safe_member(directory, "manifest.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest must be an object")
            if payload.get("schema_version") != 1 or payload.get("kind") != "custom":
                raise ValueError("manifest ownership envelope is missing or unsupported")
            return CustomEventManifest.model_validate(payload)
        except (OSError, ValueError, ValidationError) as exc:
            raise _cached_invalid("The custom event manifest is missing or invalid.") from exc

    def _read_ownership_envelope(self, directory: Path, expected_event_id: str) -> None:
        path = self._safe_member(directory, "manifest.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "The custom event ownership envelope is missing or invalid.",
            ) from exc
        if not isinstance(payload, dict) or (
            payload.get("schema_version") != 1
            or payload.get("kind") != "custom"
            or payload.get("event_id") != expected_event_id
        ):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "The manifest does not explicitly own this repository path.",
            )

    def validate_directory(self, directory: Path, expected_event_id: str) -> CustomEventManifest:
        self._require_safe_id(expected_event_id)
        directory = self._require_owned_directory(Path(directory), allow_temporary=True)
        if not directory.is_dir():
            raise _cached_invalid("The custom event directory is missing.")
        manifest = self._read_manifest_envelope(directory)
        if manifest.event_id != expected_event_id:
            raise _cached_invalid("The manifest event ID does not match its repository identity.")

        event_path = self._safe_member(directory, manifest.event_file)
        provenance_path = self._safe_member(directory, manifest.provenance_file)
        if not event_path.is_file() or not provenance_path.is_file():
            raise _cached_invalid("Required processed event files are missing.")
        if sha256_file(event_path) != manifest.event_sha256:
            raise _cached_invalid("The processed event checksum does not match its manifest.")
        if sha256_file(provenance_path) != manifest.provenance_sha256:
            raise _cached_invalid("The provenance checksum does not match its manifest.")
        try:
            records = read_manifest(provenance_path)
            if not records:
                raise ValueError("provenance contains no records")
            with xr.open_dataset(event_path, engine="h5netcdf") as opened:
                dataset = opened.load()
            validate_weather_dataset(dataset)
            if dataset.attrs.get("event_id") != expected_event_id:
                raise ValueError("dataset event identity mismatch")
            if any(
                endpoint.minute not in (0, 30)
                or endpoint.second != 0
                or endpoint.microsecond != 0
                for endpoint in (manifest.start_time, manifest.end_time)
            ):
                raise ValueError("manifest endpoints are not aligned to UTC half-hours")
            elapsed = manifest.end_time - manifest.start_time
            expected_count = int(elapsed / timedelta(minutes=30)) + 1
            if elapsed <= timedelta(0) or elapsed > MAX_WINDOW:
                raise ValueError("manifest time window is invalid")
            if not (
                dataset.sizes["time"]
                == manifest.frame_count
                == manifest.expected_frame_count
                == expected_count
            ):
                raise ValueError("dataset frame count mismatch")
            expected_times = np.arange(
                np.datetime64(manifest.start_time.replace(tzinfo=None), "ns"),
                np.datetime64(manifest.end_time.replace(tzinfo=None), "ns")
                + np.timedelta64(30, "m"),
                np.timedelta64(30, "m"),
                dtype="datetime64[ns]",
            )
            actual_times = dataset.time.values.astype("datetime64[ns]")
            if not np.array_equal(actual_times, expected_times):
                raise ValueError("dataset timestamps do not match the inclusive half-hour window")
            bounds = manifest.bounding_box
            if (
                bounds.min_lat < CMORPH_MIN_LAT
                or bounds.max_lat > CMORPH_MAX_LAT
                or bounds.max_lat - bounds.min_lat > MAX_REGION_DEGREES
                or bounds.max_lon - bounds.min_lon > MAX_REGION_DEGREES
            ):
                raise ValueError("manifest bounds are outside the supported request contract")
            latitudes = np.asarray(dataset.latitude.values, dtype=float)
            longitudes = np.asarray(dataset.longitude.values, dtype=float)
            if (
                latitudes.size == 0
                or longitudes.size == 0
                or latitudes.min() < bounds.min_lat - 1e-9
                or latitudes.max() > bounds.max_lat + 1e-9
                or longitudes.min() < bounds.min_lon - 1e-9
                or longitudes.max() > bounds.max_lon + 1e-9
            ):
                raise ValueError("dataset coordinates are outside manifest bounds")
        except (OSError, KeyError, ValueError, ValidationError) as exc:
            raise _cached_invalid("The processed event or provenance structure is invalid.") from exc
        return manifest

    def validate_ready(self, event_id: str) -> CustomEventManifest:
        directory = self._custom_path(event_id)
        if directory.is_symlink():
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "Symlinked event directories are not allowed.")
        return self.validate_directory(directory, event_id)

    def promote(self, temporary: Path, event_id: str) -> Path:
        final = self._custom_path(event_id)
        if any(item.id == event_id for item in self._catalog().events):
            raise EventOperationError(
                EventErrorCode.BUILTIN_EVENT_PROTECTED,
                "Custom events cannot replace a built-in event identity.",
            )
        temporary = self._require_owned_directory(Path(temporary), allow_temporary=True)
        if not temporary.name.startswith(f".tmp-{event_id}-"):
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "The temporary event directory name is invalid.")
        self.validate_directory(temporary, event_id)
        if final.exists() or final.is_symlink():
            raise _cached_invalid("A repository event already exists for this request.")
        try:
            temporary.replace(final)
        except OSError as exc:
            raise EventOperationError(
                EventErrorCode.EVENT_STORAGE_FAILED,
                "The prepared event could not be promoted into the repository.",
                details={"event_id": event_id},
            ) from exc
        return final

    def delete(self, event_id: str) -> None:
        if any(item.id == event_id for item in self._catalog().events):
            raise EventOperationError(EventErrorCode.BUILTIN_EVENT_PROTECTED, "Built-in events cannot be deleted.")
        directory = self._custom_path(event_id)
        if not directory.exists() and not directory.is_symlink():
            raise EventOperationError(EventErrorCode.EVENT_NOT_FOUND, "The requested event does not exist.")
        directory = self._require_owned_directory(directory, allow_temporary=False)
        if not directory.is_dir():
            raise EventOperationError(EventErrorCode.UNSAFE_EVENT_PATH, "The custom event path is not a directory.")
        self._read_ownership_envelope(directory, event_id)
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            raise EventOperationError(
                EventErrorCode.EVENT_STORAGE_FAILED,
                "The custom event could not be removed from storage.",
                details={"event_id": event_id},
            ) from exc
