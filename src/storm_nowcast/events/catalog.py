from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from storm_nowcast.models.schemas import _as_utc


class EventRecord(BaseModel):
    id: str
    name: str
    region: str
    observation_start: datetime
    observation_end: datetime
    sources: list[str] = Field(min_length=1)
    frame_count: int = Field(gt=0)
    data_path: Path
    insat_data_path: Path | None = None
    insat_max_age_minutes: int = Field(default=30, ge=0, le=360)
    limitations: list[str] = Field(default_factory=list)

    _utc_times = field_validator("observation_start", "observation_end", mode="before")(_as_utc)


class EventCatalog(BaseModel):
    events: list[EventRecord]

    def get(self, event_id: str) -> EventRecord:
        for event in self.events:
            if event.id == event_id:
                return event
        raise KeyError(f"Unknown event: {event_id}")


def load_event_catalog(path: Path) -> EventCatalog:
    path = Path(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    project_root = path.resolve().parent.parent
    for item in payload.get("events", []):
        for field in ("data_path", "insat_data_path"):
            if not item.get(field):
                continue
            data_path = Path(item[field])
            if not data_path.is_absolute():
                item[field] = project_root / data_path
    return EventCatalog.model_validate(payload)
