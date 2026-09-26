from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable

import numpy as np
import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.data.cmorph_cache import CmorphCache, CachedCmorphAsset
from storm_nowcast.data.provenance import sha256_file, write_manifest
from storm_nowcast.events.custom import (
    CustomEventManifest,
    CustomEventRequest,
    EventLibraryRecord,
    custom_event_id,
    required_cmorph_hours,
    validate_custom_event_request,
)
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.events.locking import EventBuildLock
from storm_nowcast.events.repository import EventRepository
from storm_nowcast.models.schemas import ProvenanceRecord
from storm_nowcast.replay.player import ReplayPlayer, save_event


class BuildStage(StrEnum):
    CHECKING_ARCHIVE = "Checking archive"
    VALIDATING_CACHE = "Validating cached observations"
    DOWNLOADING = "Downloading official observations"
    CROPPING_REGION = "Cropping study region"
    PREPARING_EVENT = "Preparing event atomically"
    DETECTING_TRACKING = "Detecting and tracking cells"
    BUILDING_FORECASTS = "Building available forecasts"
    COMPLETE = "Complete"


ProgressCallback = Callable[[BuildStage], None]


@dataclass(frozen=True)
class PreparedCustomEvent:
    manifest: CustomEventManifest
    record: EventLibraryRecord
    created: bool
    reused: bool


class CmorphEventBuilder:
    """Synchronous, UI-agnostic transaction for one canonical CMORPH event."""

    def __init__(
        self,
        repository: EventRepository,
        cache: CmorphCache,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.settings = settings
        self.clock = clock

    @staticmethod
    def _emit(progress: ProgressCallback | None, stage: BuildStage) -> None:
        if progress is not None:
            progress(stage)

    @staticmethod
    def _normalize_dataset(
        assets: list[CachedCmorphAsset], request: CustomEventRequest, event_id: str
    ) -> xr.Dataset:
        combined = xr.concat([asset.dataset for asset in assets], dim="time").sortby("time")
        times = combined.time.values.astype("datetime64[ns]")
        _, unique_indices = np.unique(times, return_index=True)
        combined = combined.isel(time=np.sort(unique_indices))
        start = np.datetime64(request.start_time.replace(tzinfo=None), "ns")
        end = np.datetime64(request.end_time.replace(tzinfo=None), "ns")
        combined = combined.sel(time=slice(start, end)).load()
        expected = np.arange(
            start,
            end + np.timedelta64(30, "m"),
            np.timedelta64(30, "m"),
            dtype="datetime64[ns]",
        )
        actual = combined.time.values.astype("datetime64[ns]")
        if not np.array_equal(actual, expected):
            raise EventOperationError(
                EventErrorCode.NOAA_FILE_CORRUPT,
                "Official CMORPH observations do not contain the exact requested timestamps.",
                details={"expected_frames": len(expected), "actual_frames": len(actual)},
            )
        values = np.asarray(combined.rain_rate.values, dtype=np.float32)
        combined["rain_rate"] = (("time", "latitude", "longitude"), values)
        combined["missing_mask"] = (
            ("time", "latitude", "longitude"),
            ~np.isfinite(values),
        )
        combined.attrs.update(
            {
                "event_id": event_id,
                "observation_start": request.start_time.isoformat().replace("+00:00", "Z"),
                "observation_end": request.end_time.isoformat().replace("+00:00", "Z"),
                "provider": "NOAA Climate Prediction Center",
                "product": "CMORPH V0.x RAW 8km-30min",
                "source_resolution": "~8 km grid spacing; effective source resolution is coarser",
                "crs": "EPSG:4326",
                "is_synthetic": False,
            }
        )
        return combined

    @staticmethod
    def _provenance(assets: list[CachedCmorphAsset]) -> list[ProvenanceRecord]:
        records = []
        for asset in assets:
            hour = asset.dataset.time.values[0].astype("datetime64[ns]").astype(np.int64)
            start = datetime.fromtimestamp(hour / 1_000_000_000, tz=timezone.utc)
            action = "reused validated shared cache" if asset.reused else "downloaded and validated"
            records.append(
                ProvenanceRecord(
                    provider="NOAA Climate Prediction Center",
                    product="CMORPH V0.x RAW 8km-30min",
                    source_url=asset.official_url,
                    acquired_at=asset.acquired_at,
                    observation_start=start,
                    observation_end=start + timedelta(minutes=30),
                    sha256=asset.sha256,
                    local_file=str(asset.path),
                    processing_steps=[
                        action,
                        "validated compressed binary layout and checksum",
                        "cropped to requested bounds without spatial upsampling",
                    ],
                    is_synthetic=False,
                )
            )
        return records

    def _analysis_summary(self, dataset: xr.Dataset) -> dict[str, object]:
        tracks = ReplayPlayer(dataset, self.settings).all_tracks()
        forecast_ready = sum(len(track.history) >= 2 for track in tracks)
        return {
            "detected_cell_count": len(tracks),
            "forecast_ready_track_count": forecast_ready,
            "track_dependent_outputs": "available" if forecast_ready else "unavailable",
        }

    @staticmethod
    def _source_summary(assets: list[CachedCmorphAsset]) -> list[dict[str, object]]:
        return [
            {
                "official_url": asset.official_url,
                "source_file": asset.path.name,
                "sha256": asset.sha256,
                "compressed_byte_count": asset.compressed_byte_count,
                "downloaded": asset.downloaded,
                "reused": asset.reused,
            }
            for asset in assets
        ]

    def prepare(
        self,
        request: CustomEventRequest,
        progress: ProgressCallback | None = None,
        *,
        allow_download: bool = True,
    ) -> PreparedCustomEvent:
        canonical = validate_custom_event_request(request, now=self.clock())
        event_id = custom_event_id(canonical)
        self._emit(progress, BuildStage.CHECKING_ARCHIVE)
        lock = EventBuildLock(self.repository.custom_root / ".locks", event_id, clock=self.clock)
        temporary: Path | None = None
        stage = BuildStage.CHECKING_ARCHIVE
        lock.acquire()
        try:
            final = self.repository.custom_root / event_id
            if final.exists() or final.is_symlink():
                manifest = self.repository.validate_ready(event_id)
                self._emit(progress, BuildStage.COMPLETE)
                return PreparedCustomEvent(
                    manifest=manifest,
                    record=self.repository.get(event_id),
                    created=False,
                    reused=True,
                )

            self.repository.custom_root.mkdir(parents=True, exist_ok=True)
            temporary = Path(
                tempfile.mkdtemp(prefix=f".tmp-{event_id}-", dir=self.repository.custom_root)
            )
            stage = BuildStage.VALIDATING_CACHE
            self._emit(progress, stage)
            stage = BuildStage.DOWNLOADING
            self._emit(progress, stage)
            assets = [
                self.cache.get(hour, canonical.bounds, allow_download=allow_download)
                for hour in required_cmorph_hours(canonical)
            ]
            stage = BuildStage.CROPPING_REGION
            self._emit(progress, stage)
            dataset = self._normalize_dataset(assets, canonical, event_id)
            stage = BuildStage.PREPARING_EVENT
            self._emit(progress, stage)
            event_path = temporary / "event.nc"
            provenance_path = temporary / "provenance.json"
            save_event(dataset, event_path)
            write_manifest(provenance_path, self._provenance(assets))
            stage = BuildStage.DETECTING_TRACKING
            self._emit(progress, stage)
            analysis_summary = self._analysis_summary(dataset)
            stage = BuildStage.BUILDING_FORECASTS
            self._emit(progress, stage)
            manifest = CustomEventManifest(
                event_id=event_id,
                display_name=canonical.event_name or f"CMORPH region {canonical.start_time:%Y-%m-%d %H:%MZ}",
                bounding_box=canonical.bounds,
                start_time=canonical.start_time,
                end_time=canonical.end_time,
                expected_frame_count=canonical.expected_frame_count,
                frame_count=dataset.sizes["time"],
                provider="NOAA Climate Prediction Center",
                source_product="CMORPH V0.x RAW 8km-30min",
                native_resolution="~8 km grid spacing; effective source resolution is coarser",
                created_at=self.clock(),
                event_sha256=sha256_file(event_path),
                provenance_sha256=sha256_file(provenance_path),
                stored_bytes=event_path.stat().st_size + provenance_path.stat().st_size,
                analysis_ready=True,
                analysis_summary=analysis_summary,
                source_files=self._source_summary(assets),
                limitations=[
                    "Rainfall-only deterministic analysis; not an operational warning.",
                    "Track-dependent outputs require at least two observations of a detected cell.",
                ],
            )
            (temporary / "manifest.json").write_text(
                manifest.model_dump_json(indent=2), encoding="utf-8"
            )
            self.repository.validate_directory(temporary, event_id)
            self.repository.promote(temporary, event_id)
            temporary = None
            record = self.repository.get(event_id)
            self._emit(progress, BuildStage.COMPLETE)
            return PreparedCustomEvent(
                manifest=manifest,
                record=record,
                created=True,
                reused=False,
            )
        except EventOperationError:
            raise
        except Exception as exc:
            raise EventOperationError(
                EventErrorCode.EVENT_STORAGE_FAILED,
                "Custom event preparation failed safely.",
                details={"event_id": event_id, "stage": stage.value},
            ) from exc
        finally:
            if temporary is not None and temporary.exists():
                parent = temporary.parent.resolve()
                if parent == self.repository.custom_root and temporary.name.startswith(f".tmp-{event_id}-"):
                    shutil.rmtree(temporary)
            lock.release()
