"""
lock.py – Robust, Windows-compatible file locking for FanCode Monitor (Phase 10).

Prevents concurrent pipeline executions and provides safe stale lock recovery.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.monitor.exceptions import LockAcquisitionError

logger = logging.getLogger(__name__)


def is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is currently active."""
    if pid <= 0:
        return False

    if platform.system() == "Windows":
        try:
            # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION, 0x0400 = PROCESS_QUERY_INFORMATION
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class MonitorLock:
    """
    Exclusive file lock preventing concurrent monitor runs on the same machine.
    """

    def __init__(
        self,
        lock_file: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self.lock_file = Path(lock_file or getattr(settings, "MONITOR_LOCK_FILE", "data/monitor.lock"))
        self.timeout_seconds = timeout_seconds or getattr(settings, "MONITOR_LOCK_TIMEOUT_SECONDS", 1800)
        self.run_id = run_id
        self._is_acquired = False

    def acquire(self, blocking: bool = False, wait_timeout: int = 5) -> bool:
        """
        Attempts to acquire the exclusive lock.
        Returns True if acquired successfully, False if already locked.
        """
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        while True:
            if not self.lock_file.exists():
                if self._write_lock_file():
                    self._is_acquired = True
                    logger.debug("Acquired monitor lock at %s", self.lock_file)
                    return True

            # Lock file exists; check if stale
            lock_info = self.get_lock_info()
            if lock_info:
                if self._is_stale(lock_info):
                    logger.warning(
                        "Reclaiming stale lock file (held by PID %s, created at %s)",
                        lock_info.get("pid"),
                        lock_info.get("created_at"),
                    )
                    self._remove_lock_file()
                    if self._write_lock_file():
                        self._is_acquired = True
                        return True
                else:
                    # Active lock held by living process
                    if not blocking or (time.time() - start_time) >= wait_timeout:
                        logger.warning(
                            "Cannot acquire lock: another monitor is active (PID %s, run %s)",
                            lock_info.get("pid"),
                            lock_info.get("run_id"),
                        )
                        return False
            else:
                # Empty, truncated, or invalid JSON cannot represent a live
                # owner. Recover it immediately instead of permanently
                # blocking every future monitor run.
                logger.warning("Reclaiming corrupt or empty lock file: %s", self.lock_file)
                self._remove_lock_file()
                if self._write_lock_file():
                    self._is_acquired = True
                    return True

            if blocking:
                time.sleep(0.5)
            else:
                return False

    def release(self) -> None:
        """Releases the lock file if owned by current process."""
        if not self._is_acquired:
            return

        lock_info = self.get_lock_info()
        if lock_info and lock_info.get("pid") == os.getpid():
            self._remove_lock_file()
            logger.debug("Released monitor lock at %s", self.lock_file)

        self._is_acquired = False

    def is_locked(self) -> bool:
        """Returns True if a valid active lock currently exists."""
        if not self.lock_file.exists():
            return False
        info = self.get_lock_info()
        if not info:
            return False
        return not self._is_stale(info)

    def get_lock_info(self) -> Optional[Dict[str, Any]]:
        """Reads lock metadata from disk."""
        if not self.lock_file.exists():
            return None
        try:
            with open(self.lock_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_lock_file(self) -> bool:
        """Atomically writes current process metadata to lock file."""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "pid": os.getpid(),
            "created_at": now,
            "hostname": socket.gethostname(),
            "run_id": self.run_id or str(os.getpid()),
        }
        try:
            # Use exclusive file creation mode ('x') for atomicity
            with open(self.lock_file, "x", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except FileExistsError:
            return False
        except Exception as e:
            logger.error("Failed to write lock file %s: %s", self.lock_file, e)
            return False

    def _remove_lock_file(self) -> None:
        """Safely removes the lock file."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Error deleting lock file %s: %s", self.lock_file, e)

    def _is_stale(self, lock_info: Dict[str, Any]) -> bool:
        """Checks if lock is stale due to dead PID or TTL expiration."""
        pid = lock_info.get("pid")
        if pid and not is_process_alive(int(pid)):
            return True

        created_str = lock_info.get("created_at")
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str)
                elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
                if elapsed > self.timeout_seconds:
                    return True
            except Exception:
                return True

        return False

    def __enter__(self) -> MonitorLock:
        if not self.acquire():
            raise LockAcquisitionError("Failed to acquire monitor lock: another process is running.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
