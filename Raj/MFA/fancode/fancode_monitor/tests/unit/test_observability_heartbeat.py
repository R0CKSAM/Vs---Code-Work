"""
test_observability_heartbeat.py – Unit tests for HeartbeatManager and pipeline liveness (Phase 11).
"""

from __future__ import annotations

import time
from app.observability.heartbeat import HeartbeatManager


class TestHeartbeatManager:
    def test_touch_creates_heartbeat_file(self, tmp_path):
        hb_file = tmp_path / "test.heartbeat"
        mgr = HeartbeatManager(filepath=str(hb_file))

        assert mgr.read() is None
        mgr.touch(stage="schedule", cycle=1, run_id="run-hb-1")

        data = mgr.read()
        assert data is not None
        assert data["stage"] == "schedule"
        assert data["cycle"] == 1
        assert data["run_id"] == "run-hb-1"
        assert data["pid"] > 0
        assert data["uptime_seconds"] >= 0.0

    def test_freshness_evaluation(self, tmp_path):
        hb_file = tmp_path / "test_fresh.heartbeat"
        mgr = HeartbeatManager(filepath=str(hb_file))

        mgr.touch(stage="live_now")
        assert mgr.is_fresh(max_age_seconds=5) is True

    def test_clear_removes_heartbeat(self, tmp_path):
        hb_file = tmp_path / "test_clear.heartbeat"
        mgr = HeartbeatManager(filepath=str(hb_file))

        mgr.touch(stage="done")
        assert hb_file.exists()

        mgr.clear()
        assert not hb_file.exists()
        assert mgr.read() is None
