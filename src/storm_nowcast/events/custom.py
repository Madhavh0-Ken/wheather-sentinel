from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pyproj import Geod

from storm_nowcast.config import Bounds
from storm_nowcast.events.errors import EventErrorCode, EventOperationError


CMORPH_MIN_LAT = -59.963614
CMORPH_MAX_LAT = 59.963615296
CMORPH_ARCHIVE_START = datetime(2023, 1, 1, tzinfo=timezone.utc)
MAX_REGION_DEGREES = 20.0
MAX_WINDOW = timedelta(hours=24)
HALF_HOUR = timedelta(minutes=30)
WGS84 = Geod(ellps="WGS84")


class SizeUnit(StrEnum):
    DEGREES = "degrees"
    KILOMETRES = "kilometres"


class CustomEventRequest(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    start_time: datetime
    end_time: datetime
    event_name: str | None = None

    @property
    def bounds(self) -> Bounds:
        return Bounds(
            min_lat=self.min_lat,
            max_lat=self.max_lat,
            min_lon=self.min_lon,
            max_lon=self.max_lon,
        )

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.min_lat + self.max_lat) / 2.0,
            (self.min_lon + self.max_lon) / 2.0,
        )

    @property
    def expected_frame_count(self) -> int:
        return int((self.end_time - self.start_time) / HALF_HOUR) + 1


class CustomEventManifest(BaseModel):
    """Versioned ownership and integrity envelope for a prepared custom event."""

    schema_version: Literal[1] = 1
    kind: Literal["custom"] = "custom"
    event_id: str
    display_name: str
    bounding_box: Bounds
    start_time: datetime
    end_time: datetime
    expected_frame_count: int = Field(gt=0)
    frame_count: int = Field(gt=0)
    provider: str
    source_product: str
    native_resolution: str
    created_at: datetime
    event_file: str = "event.nc"
    provenance_file: str = "provenance.json"
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stored_bytes: int = Field(ge=0)
    analysis_ready: bool
    analysis_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    _utc_times = field_validator("start_time", "end_time", "created_at", mode="before")(
        lambda value: _as_utc(value, "manifest timestamp")
    )


class EventLibraryRecord(BaseModel):
    event_id: str
    display_name: str
    kind: Literal["builtin", "custom"]
    data_path: Path
    manifest_path: Path | None = None
    ready: bool
    start_time: datetime
    end_time: datetime
    frame_count: int = Field(gt=0)
    stored_bytes: int = Field(default=0, ge=0)
    bounding_box: Bounds | None = None
    analysis_ready: bool = True

    _utc_times = field_validator("start_time", "end_time", mode="before")(
        lambda value: _as_utc(value, "event timestamp")
    )


def _error(code: EventErrorCode, message: str, **details: object) -> EventOperationError:
    return EventOperationError(code, message, details=details)


def _validate_bounds_values(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> Bounds:
    if min_lon > max_lon:
        raise _error(
            EventErrorCode.DATELINE_CROSSING,
            "Dateline-crossing bounding boxes are not supported.",
            min_lon=min_lon,
            max_lon=max_lon,
        )
    if min_lat >= max_lat or min_lon >= max_lon:
        raise _error(
            EventErrorCode.INVALID_BOUNDS,
            "Region bounds must be strictly ordered.",
        )
    if min_lon < -180.0 or max_lon > 180.0:
        raise _error(
            EventErrorCode.INVALID_BOUNDS,
            "Longitudes must lie within [-180, 180].",
        )
    if min_lat < CMORPH_MIN_LAT or max_lat > CMORPH_MAX_LAT:
        raise _error(
            EventErrorCode.OUTSIDE_CMORPH_COVERAGE,
            "Requested latitude is outside this CMORPH product's supported coverage.",
            supported_min_lat=CMORPH_MIN_LAT,
            supported_max_lat=CMORPH_MAX_LAT,
        )
    height = max_lat - min_lat
    width = max_lon - min_lon
    if height > MAX_REGION_DEGREES or width > MAX_REGION_DEGREES:
        raise _error(
            EventErrorCode.REGION_TOO_LARGE,
            "Requested region exceeds the 20° × 20° limit.",
            width_degrees=width,
            height_degrees=height,
        )
    return Bounds(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )


def bounds_from_center(
    *,
    center_lat: float,
    center_lon: float,
    width: float,
    height: float,
    unit: SizeUnit | str,
) -> Bounds:
    if width <= 0 or height <= 0:
        raise _error(EventErrorCode.INVALID_BOUNDS, "Region width and height must be positive.")
    selected_unit = SizeUnit(unit)
    if selected_unit == SizeUnit.DEGREES:
        min_lat = center_lat - height / 2.0
        max_lat = center_lat + height / 2.0
        min_lon = center_lon - width / 2.0
        max_lon = center_lon + width / 2.0
    else:
        west_lon, _, _ = WGS84.fwd(center_lon, center_lat, 270.0, width * 500.0)
        east_lon, _, _ = WGS84.fwd(center_lon, center_lat, 90.0, width * 500.0)
        _, south_lat, _ = WGS84.fwd(center_lon, center_lat, 180.0, height * 500.0)
        _, north_lat, _ = WGS84.fwd(center_lon, center_lat, 0.0, height * 500.0)
        min_lat, max_lat = south_lat, north_lat
        min_lon, max_lon = west_lon, east_lon
    return _validate_bounds_values(min_lat, max_lat, min_lon, max_lon)


def _as_utc(value: datetime | str, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _error(
                EventErrorCode.INVALID_TIME_WINDOW,
                f"{field} must be a valid UTC timestamp.",
                field=field,
            ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error(
            EventErrorCode.INVALID_TIME_WINDOW,
            f"{field} must be timezone-aware UTC.",
            field=field,
        )
    return value.astimezone(timezone.utc)


def _is_half_hour(value: datetime) -> bool:
    return value.minute in (0, 30) and value.second == 0 and value.microsecond == 0


def _latest_complete_half_hour(now: datetime) -> datetime:
    utc = _as_utc(now, "now")
    minute = 30 if utc.minute >= 30 else 0
    return utc.replace(minute=minute, second=0, microsecond=0)


def validate_custom_event_request(
    request: CustomEventRequest,
    *,
    now: datetime,
) -> CustomEventRequest:
    bounds = _validate_bounds_values(
        request.min_lat,
        request.max_lat,
        request.min_lon,
        request.max_lon,
    )
    start = _as_utc(request.start_time, "start_time")
    end = _as_utc(request.end_time, "end_time")
    if not _is_half_hour(start) or not _is_half_hour(end):
        raise _error(
            EventErrorCode.INVALID_TIME_WINDOW,
            "Start and end must align to :00 or :30 UTC.",
        )
    if end <= start or end - start > MAX_WINDOW:
        raise _error(
            EventErrorCode.INVALID_TIME_WINDOW,
            "End must be after start and the inclusive window may span at most 24 hours.",
        )
    if start < CMORPH_ARCHIVE_START or end > _latest_complete_half_hour(now):
        raise _error(
            EventErrorCode.UNSUPPORTED_ARCHIVE_DATE,
            "Requested time is outside the accessible CMORPH archive period.",
            archive_start=CMORPH_ARCHIVE_START.isoformat(),
            latest_complete_half_hour=_latest_complete_half_hour(now).isoformat(),
        )
    name = request.event_name.strip() if request.event_name else None
    return request.model_copy(
        update={
            "min_lat": bounds.min_lat,
            "max_lat": bounds.max_lat,
            "min_lon": bounds.min_lon,
            "max_lon": bounds.max_lon,
            "start_time": start,
            "end_time": end,
            "event_name": name or None,
        }
    )


def required_cmorph_hours(request: CustomEventRequest) -> tuple[datetime, ...]:
    first = request.start_time.replace(minute=0, second=0, microsecond=0)
    last = request.end_time.replace(minute=0, second=0, microsecond=0)
    count = int((last - first) / timedelta(hours=1)) + 1
    return tuple(first + timedelta(hours=index) for index in range(count))


def _coordinate_token(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    return f"{abs(value):.2f}".replace(".", "p") + hemisphere


def custom_event_id(request: CustomEventRequest) -> str:
    center_lat, center_lon = request.center
    canonical = json.dumps(
        {
            "bounds": [
                round(request.min_lat, 8),
                round(request.max_lat, 8),
                round(request.min_lon, 8),
                round(request.max_lon, 8),
            ],
            "start_time": request.start_time.isoformat(),
            "end_time": request.end_time.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    return (
        f"cmorph-custom-{request.start_time:%Y%m%dT%H%MZ}-"
        f"{_coordinate_token(center_lat, 'N', 'S')}-"
        f"{_coordinate_token(center_lon, 'E', 'W')}-{digest}"
    )
