"""
test_monitor_scheduler.py – Unit tests for MonitorRunner, one-shot mode, and scheduling loop (Phase 10).
"""

from __future__ import annotations

import pytest
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineRunResult, PipelineStatus
from app.monitor.pipeline import MonitorPipeline
from app.monitor.runner import MonitorRunner
from app.monitor.stages import BaseStage, PipelineContext, StageResult


class DummyStage(BaseStage):
    name = "dummy"
    def run(self, context: PipelineContext) -> StageResult:
        return StageResult(name=self.name, records_processed=1)


class TestMonitorScheduler:
    def test_run_once_executes_and_releases_lock(self, db_session, tmp_path):
        lock_file = tmp_path / "sched.lock"
        lock = MonitorLock(lock_file=str(lock_file))
        pipeline = MonitorPipeline(session=db_session, stages=[DummyStage()])
        runner = MonitorRunner(pipeline=pipeline, lock=lock)

        result = runner.run_once()
        assert result.status == PipelineStatus.SUCCESS
        assert not lock.is_locked()

    def test_run_once_skipped_when_already_locked(self, db_session, tmp_path):
        lock_file = tmp_path / "sched_held.lock"
        lock1 = MonitorLock(lock_file=str(lock_file))
        lock1.acquire()

        lock2 = MonitorLock(lock_file=str(lock_file))
        pipeline = MonitorPipeline(session=db_session, stages=[DummyStage()])
        runner = MonitorRunner(pipeline=pipeline, lock=lock2)

        result = runner.run_once()
        assert result.status == PipelineStatus.SKIPPED
        assert "Active lock" in (result.error_summary or "")

        lock1.release()

    def test_run_loop_respects_max_cycles(self, db_session, tmp_path):
        lock_file = tmp_path / "sched_loop.lock"
        lock = MonitorLock(lock_file=str(lock_file))
        pipeline = MonitorPipeline(session=db_session, stages=[DummyStage()])
        runner = MonitorRunner(pipeline=pipeline, lock=lock)

        results = runner.run_loop(interval_seconds=1, max_cycles=2)
        assert len(results) == 2
        assert all(r.status == PipelineStatus.SUCCESS for r in results)
        assert not lock.is_locked()
