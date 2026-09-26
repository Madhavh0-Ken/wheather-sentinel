from __future__ import annotations

from pathlib import Path

import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.events.catalog import EventCatalog, EventRecord, load_event_catalog
from storm_nowcast.events.repository import EventRepository
from storm_nowcast.events.custom import EventLibraryRecord
from storm_nowcast.services.analysis import AnalysisService


class EventDataUnavailable(RuntimeError):
    pass


def optional_catalog(path: Path) -> EventCatalog:
    if not Path(path).exists():
        return EventCatalog(events=[])
    return load_event_catalog(path)


def load_analysis_service(settings: Settings, catalog: EventCatalog) -> AnalysisService:
    if not settings.data.processed_event.exists():
        raise EventDataUnavailable(
            f"No prepared CMORPH event is available at {settings.data.processed_event}. "
            "Run `python scripts/prepare_demo.py` while connected, then retry."
        )
    dataset = xr.load_dataset(settings.data.processed_event, engine="h5netcdf")
    event_id = str(dataset.attrs.get("event_id", "cmorph-cached-event"))
    return AnalysisService.from_dataset(dataset, settings=settings, event_id=event_id)


def repository_event_identity(
    repository: EventRepository,
    event_id: str,
) -> tuple[EventLibraryRecord, str]:
    record = repository.get(event_id)
    if not record.ready or not record.data_path.is_file():
        raise EventDataUnavailable(f"Prepared event data are unavailable for {event_id}.")
    checksum = (
        repository.validate_ready(event_id).event_sha256
        if record.kind == "custom"
        else sha256_file(record.data_path)
    )
    return record, checksum


def load_repository_analysis_service(
    settings: Settings,
    repository: EventRepository,
    event_id: str,
) -> tuple[AnalysisService, str]:
    record, checksum = repository_event_identity(repository, event_id)
    dataset = xr.load_dataset(record.data_path, engine="h5netcdf")
    return (
        AnalysisService.from_dataset(dataset, settings=settings, event_id=event_id),
        checksum,
    )
