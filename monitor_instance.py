"""Process-wide guard for a single NCU Gym Monitor instance."""

from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path
from typing import BinaryIO


class MonitorInstance:
    """Owns the operating-system file lock for one Monitor instance."""

    def __init__(self, handle: BinaryIO) -> None:
        self._handle = handle
        self._released = False

    @classmethod
    def try_acquire(cls) -> "MonitorInstance | None":
        lock_path = Path(tempfile.gettempdir()) / "ncu-gym-monitor.lock"
        handle = lock_path.open("a+b")
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)

        try:
            _lock(handle)
        except OSError as error:
            handle.close()
            if error.errno in (errno.EACCES, errno.EAGAIN):
                return None
            raise

        return cls(handle)

    def release(self) -> None:
        if self._released:
            return
        try:
            self._handle.seek(0)
            _unlock(self._handle)
        finally:
            self._released = True
            self._handle.close()


if os.name == "nt":
    import msvcrt

    def _lock(handle: BinaryIO) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: BinaryIO) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(handle: BinaryIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: BinaryIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
