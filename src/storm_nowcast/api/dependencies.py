from __future__ import annotations

from pathlib import Path

import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.data.insat_replay import build_insat_replay_cube
from storm_nowcast.data.provenance import sha256_file
from storm_nowcast.events.catalog import EventCatalog, EventRecord, load_event_catalog
from storm_nowcast.events.repository import EventRepository
from storm_nowcast.events.custom import EventLibraryRecord
from storm_nowcast.services.analysis import AnalysisService


class EventDataUnavailable(RuntimeError):
    pass


def _event_satellite_cube(dataset: xr.Dataset, record: EventRecord | EventLibraryRecord) -> xr.Dataset | None:
    if record.insat_data_path is None:
        return None
    return build_insat_replay_cube(
        record.insat_data_path,
        target_times=tuple(dataset.time.values.astype("datetime64[ns]")),
        event_start=record.observation_start if isinstance(record, EventRecord) else record.start_time,
        event_end=record.observation_end if isinstance(record, EventRecord) else record.end_time,
        max_age_minutes=record.insat_max_age_minutes,
    )


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
    try:
        record = catalog.get(event_id)
    except KeyError:
        satellite_cube = None
    else:
        satellite_cube = _event_satellite_cube(dataset, record)
    return AnalysisService.from_dataset(
        dataset,
        settings=settings,
        event_id=event_id,
        satellite_cube=satellite_cube,
    )


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
        AnalysisService.from_dataset(
            dataset,
            settings=settings,
            event_id=event_id,
            satellite_cube=_event_satellite_cube(dataset, record),
        ),
        checksum,
    )
