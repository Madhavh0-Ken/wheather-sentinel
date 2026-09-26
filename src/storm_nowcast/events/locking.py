from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from storm_nowcast.events.errors import EventErrorCode, EventOperationError


DEFAULT_STALE_AFTER = timedelta(hours=2)


class EventBuildLock:
    """A filesystem lock with owner-aware release and bounded stale recovery."""

    def __init__(
        self,
        lock_root: Path,
        event_id: str,
        *,
        clock: Callable[[], datetime] | None = None,
        owner_token: str | None = None,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> None:
        self.lock_root = Path(lock_root)
        self.event_id = event_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.owner_token = owner_token or uuid.uuid4().hex
        self.stale_after = stale_after
        self.path = self.lock_root / f"{event_id}.lock"
        self._recovery_path = self.lock_root / f".{event_id}.recovery"

    def _metadata(self) -> dict[str, object]:
        now = self.clock().astimezone(timezone.utc)
        return {
            "event_id": self.event_id,
            "owner_token": self.owner_token,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "acquired_at": now.isoformat(),
        }

    @staticmethod
    def _read(path: Path) -> dict[str, object] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError):
            return None

    def _is_stale(self, metadata: dict[str, object] | None) -> bool:
        if not metadata or not isinstance(metadata.get("acquired_at"), str):
            return True
        try:
            acquired = datetime.fromisoformat(str(metadata["acquired_at"]).replace("Z", "+00:00"))
            if acquired.tzinfo is None:
                return True
            return self.clock().astimezone(timezone.utc) - acquired.astimezone(timezone.utc) > self.stale_after
        except ValueError:
            return True

    @staticmethod
    def _write_exclusive(path: Path, metadata: dict[str, object]) -> None:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())

    def _in_progress(self) -> EventOperationError:
        return EventOperationError(
            EventErrorCode.EVENT_BUILD_IN_PROGRESS,
            "This event is already being prepared.",
            details={"event_id": self.event_id, "lock": self._read(self.path) or {}},
        )

    def acquire(self) -> "EventBuildLock":
        self.lock_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_exclusive(self.path, self._metadata())
            return self
        except FileExistsError:
            pass
        if not self._is_stale(self._read(self.path)):
            raise self._in_progress()

        # One bounded recovery attempt serializes stale replacement.
        try:
            self._write_exclusive(self._recovery_path, self._metadata())
        except FileExistsError:
            raise self._in_progress()
        try:
            if self.path.exists() and not self._is_stale(self._read(self.path)):
                raise self._in_progress()
            try:
                self.path.unlink(missing_ok=True)
                self._write_exclusive(self.path, self._metadata())
            except FileExistsError:
                raise self._in_progress()
            return self
        finally:
            recovery = self._read(self._recovery_path)
            if recovery and recovery.get("owner_token") == self.owner_token:
                self._recovery_path.unlink(missing_ok=True)

    def release(self) -> None:
        metadata = self._read(self.path)
        if metadata and metadata.get("owner_token") == self.owner_token:
            self.path.unlink(missing_ok=True)

    def __enter__(self) -> "EventBuildLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()
