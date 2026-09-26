from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from storm_nowcast.models.schemas import _as_utc


class LiveFrame(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source: str
    timestamp: datetime
    payload_ref: Any

    _utc_timestamp = field_validator("timestamp", mode="before")(_as_utc)


class LiveProvider(Protocol):
    def fetch_latest(self, after: datetime | None = None) -> LiveFrame | None: ...


class SourceHealth(BaseModel):
    status: Literal["CURRENT", "STALE_CACHE", "UNAVAILABLE", "RATE_LIMITED"]
    last_observation_time: datetime | None = None
    last_attempt_time: datetime
    error: str | None = None


class LivePollResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    accepted_frames: list[LiveFrame]
    sources: dict[str, SourceHealth]


class LiveRunner:
    def __init__(
        self,
        providers: dict[str, LiveProvider],
        *,
        retry_attempts: int = 2,
        stale_after_minutes: int = 60,
        minimum_poll_interval_seconds: int = 60,
    ) -> None:
        self.providers = providers
        self.retry_attempts = retry_attempts
        self.stale_after = timedelta(minutes=stale_after_minutes)
        self.minimum_poll_interval = timedelta(seconds=minimum_poll_interval_seconds)
        self.last_frames: dict[str, LiveFrame] = {}
        self.last_attempts: dict[str, datetime] = {}
        self.health: dict[str, SourceHealth] = {}

    def poll_once(self, *, now: datetime) -> LivePollResult:
        now = _as_utc(now)
        accepted: list[LiveFrame] = []
        for name, provider in self.providers.items():
            previous_attempt = self.last_attempts.get(name)
            cached = self.last_frames.get(name)
            if previous_attempt is not None and now - previous_attempt < self.minimum_poll_interval:
                self.health[name] = SourceHealth(
                    status="RATE_LIMITED",
                    last_observation_time=cached.timestamp if cached else None,
                    last_attempt_time=previous_attempt,
                )
                continue
            self.last_attempts[name] = now
            frame: LiveFrame | None = None
            error: str | None = None
            for _ in range(self.retry_attempts):
                try:
                    frame = provider.fetch_latest(after=cached.timestamp if cached else None)
                    error = None
                    break
                except Exception as exc:
                    error = str(exc)
            if frame is not None and (cached is None or frame.timestamp > cached.timestamp):
                self.last_frames[name] = frame
                cached = frame
                accepted.append(frame)
            if error is not None:
                status = "STALE_CACHE" if cached is not None and now - cached.timestamp <= self.stale_after else "UNAVAILABLE"
            else:
                status = "CURRENT" if cached is not None else "UNAVAILABLE"
            self.health[name] = SourceHealth(
                status=status,
                last_observation_time=cached.timestamp if cached else None,
                last_attempt_time=now,
                error=error,
            )
        return LivePollResult(accepted_frames=accepted, sources=dict(self.health))
