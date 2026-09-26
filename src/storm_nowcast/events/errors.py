from __future__ import annotations

from enum import StrEnum
from typing import Any


class EventErrorCode(StrEnum):
    INVALID_BOUNDS = "INVALID_BOUNDS"
    REGION_TOO_LARGE = "REGION_TOO_LARGE"
    OUTSIDE_CMORPH_COVERAGE = "OUTSIDE_CMORPH_COVERAGE"
    DATELINE_CROSSING = "DATELINE_CROSSING"
    INVALID_TIME_WINDOW = "INVALID_TIME_WINDOW"
    UNSUPPORTED_ARCHIVE_DATE = "UNSUPPORTED_ARCHIVE_DATE"
    EVENT_BUILD_IN_PROGRESS = "EVENT_BUILD_IN_PROGRESS"
    NOAA_UNAVAILABLE = "NOAA_UNAVAILABLE"
    NOAA_FILE_CORRUPT = "NOAA_FILE_CORRUPT"
    CACHED_EVENT_INVALID = "CACHED_EVENT_INVALID"
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    BUILTIN_EVENT_PROTECTED = "BUILTIN_EVENT_PROTECTED"
    UNSAFE_EVENT_PATH = "UNSAFE_EVENT_PATH"
    EVENT_STORAGE_FAILED = "EVENT_STORAGE_FAILED"


class EventOperationError(ValueError):
    def __init__(
        self,
        code: EventErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }
