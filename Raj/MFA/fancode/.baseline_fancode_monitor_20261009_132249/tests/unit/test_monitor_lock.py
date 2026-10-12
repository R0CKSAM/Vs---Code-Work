"""
test_monitor_lock.py – Unit tests for MonitorLock concurrency control and stale lock recovery (Phase 10).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
import pytest

from app.monitor.exceptions import LockAcquisitionError
from app.monitor.lock import MonitorLock


class TestMonitorLock:
    def test_acquire_and_release_lock(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock = MonitorLock(lock_file=str(lock_file))

        assert lock.acquire() is True
        assert lock_file.exists()
        assert lock.is_locked() is True

        lock.release()
        assert not lock_file.exists()
        assert lock.is_locked() is False

    def test_concurrent_lock_acquisition_rejected(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock1 = MonitorLock(lock_file=str(lock_file))
        lock2 = MonitorLock(lock_file=str(lock_file))

        assert lock1.acquire() is True
        # Second process/instance cannot acquire active lock
        assert lock2.acquire(blocking=False) is False

        lock1.release()
        # Now lock2 can acquire
        assert lock2.acquire(blocking=False) is True
        lock2.release()

    def test_context_manager_usage(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        with MonitorLock(lock_file=str(lock_file)) as lock:
            assert lock.is_locked() is True

        assert not lock_file.exists()

    def test_context_manager_raises_on_held_lock(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock1 = MonitorLock(lock_file=str(lock_file))
        lock1.acquire()

        with pytest.raises(LockAcquisitionError):
            with MonitorLock(lock_file=str(lock_file)):
                pass

        lock1.release()

    def test_stale_lock_with_dead_pid_is_reclaimed(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        # Write lock file with a non-existent dead PID (e.g. 99999999)
        fake_lock_data = {
            "pid": 99999999,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "hostname": "test-host",
            "run_id": "stale-run-123",
        }
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump(fake_lock_data, f)

        lock = MonitorLock(lock_file=str(lock_file))
        # Lock should detect dead PID and safely acquire
        assert lock.acquire() is True
        info = lock.get_lock_info()
        assert info["pid"] == os.getpid()
        lock.release()

    def test_stale_lock_expired_ttl_is_reclaimed(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        # Write lock file from 2 hours ago
        fake_lock_data = {
            "pid": os.getpid(),
            "created_at": "2020-01-01T00:00:00Z",
            "hostname": "test-host",
            "run_id": "expired-run-123",
        }
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump(fake_lock_data, f)

        lock = MonitorLock(lock_file=str(lock_file), timeout_seconds=10)
        assert lock.acquire() is True
        lock.release()
