from __future__ import annotations

import json
import os
import re
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator

from storm_nowcast.events.errors import EventErrorCode, EventOperationError


DEFAULT_STALE_AFTER = timedelta(hours=2)
SAFE_LOCK_ID = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def _is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        stat_result = path.lstat()
        attributes = getattr(stat_result, "st_file_attributes", 0)
        reparse_flag = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if not attributes & reparse_flag:
            return False
        reparse_tag = getattr(stat_result, "st_reparse_tag", None)
        if reparse_tag is None:
            return True
        # Windows name-surrogate tags redirect pathname resolution. Cloud-file
        # placeholder tags are reparse points too, but do not redirect paths.
        return bool(reparse_tag & 0x20000000)
    except OSError:
        return False


@contextmanager
def _transition_guard(lock_root: Path, event_id: str) -> Iterator[None]:
    """Serialize lock publication/recovery/release without another lock artifact."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        identity = (
            f"{os.path.normcase(str(lock_root.resolve()))}::"
            f"{os.path.normcase(event_id)}"
        ).encode("utf-8")
        name = f"Local\\StormNowcast-{sha256(identity).hexdigest()}"
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create lock transition mutex")
        acquired = False
        try:
            result = kernel32.WaitForSingleObject(handle, 30_000)
            if result not in (0x00000000, 0x00000080):
                raise TimeoutError("Timed out waiting for lock ownership transition")
            acquired = True
            yield
        finally:
            if acquired:
                kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return

    import fcntl

    descriptor = os.open(lock_root, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


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
        if not SAFE_LOCK_ID.fullmatch(event_id):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "Lock event IDs may contain only letters, numbers, and hyphens.",
                details={"event_id": event_id},
            )
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
        if self.lock_root.exists() and _is_link_or_reparse_point(self.lock_root):
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "Symlinked or reparse-point lock directories are not allowed.",
            )
        self.lock_root.mkdir(parents=True, exist_ok=True)
        if self.lock_root.resolve(strict=True) != self.lock_root.absolute():
            raise EventOperationError(
                EventErrorCode.UNSAFE_EVENT_PATH,
                "The lock directory resolves outside its configured path.",
            )
        with _transition_guard(self.lock_root, self.event_id):
            legacy_recovery = self._read(self._recovery_path)
            if self._recovery_path.exists():
                if not self._is_stale(legacy_recovery):
                    raise self._in_progress()
                self._recovery_path.unlink(missing_ok=True)
            try:
                self._write_exclusive(self.path, self._metadata())
                return self
            except FileExistsError:
                pass
            if not self._is_stale(self._read(self.path)):
                raise self._in_progress()
            self.path.unlink(missing_ok=True)
            try:
                self._write_exclusive(self.path, self._metadata())
            except FileExistsError:
                raise self._in_progress()
            return self

    def release(self) -> None:
        if not self.lock_root.is_dir() or _is_link_or_reparse_point(self.lock_root):
            return
        with _transition_guard(self.lock_root, self.event_id):
            metadata = self._read(self.path)
            if metadata and metadata.get("owner_token") == self.owner_token:
                self.path.unlink(missing_ok=True)

    def __enter__(self) -> "EventBuildLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()
