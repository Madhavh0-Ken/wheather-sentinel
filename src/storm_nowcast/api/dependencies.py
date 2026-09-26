from __future__ import annotations

from pathlib import Path

import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.events.catalog import EventCatalog, EventRecord, load_event_catalog
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
