"""
test_monitor_pipeline.py – Unit tests for MonitorPipeline orchestration, retries, and failure isolation (Phase 10).
"""

from __future__ import annotations

import pytest
from app.monitor.exceptions import FatalPipelineError
from app.monitor.models import PipelineStatus, StageResult, StageStatus
from app.monitor.pipeline import MonitorPipeline
from app.monitor.stages import BaseStage, PipelineContext


class StageA(BaseStage):
    name = "stage_a"
    def run(self, context: PipelineContext) -> StageResult:
        return StageResult(name=self.name, records_processed=10)


class StageB(BaseStage):
    name = "stage_b"
    def run(self, context: PipelineContext) -> StageResult:
        return StageResult(name=self.name, records_processed=20)


class FailingNonFatalStage(BaseStage):
    name = "failing_stage"
    is_fatal = False
    def run(self, context: PipelineContext) -> StageResult:
        raise RuntimeError("Non-fatal failure")


class FailingFatalStage(BaseStage):
    name = "fatal_stage"
    is_fatal = True
    def run(self, context: PipelineContext) -> StageResult:
        raise RuntimeError("Fatal failure")


class FlakyStage(BaseStage):
    name = "flaky_stage"
    def __init__(self):
        self.attempts = 0
    def run(self, context: PipelineContext) -> StageResult:
        self.attempts += 1
        if self.attempts == 1:
            raise ConnectionResetError("Temporary network glitch")
        return StageResult(name=self.name, records_processed=1)


class TestMonitorPipeline:
    def test_pipeline_successful_multi_stage_run(self, db_session):
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[StageA(), StageB()],
        )
        result = pipeline.execute(trigger_type="manual")

        assert result.status == PipelineStatus.SUCCESS
        assert len(result.stages) == 2
        assert result.stages["stage_a"].status == StageStatus.SUCCESS
        assert result.stages["stage_b"].status == StageStatus.SUCCESS
        assert result.run_id is not None

    def test_failure_isolation_non_fatal_stage_continues(self, db_session):
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[StageA(), FailingNonFatalStage(), StageB()],
            max_retries=0,
        )
        result = pipeline.execute()

        # Pipeline is PARTIAL because stage_a and stage_b succeeded while failing_stage failed
        assert result.status == PipelineStatus.PARTIAL
        assert result.stages["stage_a"].status == StageStatus.SUCCESS
        assert result.stages["failing_stage"].status == StageStatus.FAILED
        assert result.stages["stage_b"].status == StageStatus.SUCCESS

    def test_fatal_stage_halts_pipeline(self, db_session):
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[StageA(), FailingFatalStage(), StageB()],
            max_retries=0,
        )
        result = pipeline.execute()

        assert result.status == PipelineStatus.FAILED
        assert result.stages["stage_a"].status == StageStatus.SUCCESS
        assert result.stages["fatal_stage"].status == StageStatus.FAILED
        assert "stage_b" not in result.stages  # Stage B never executed!

    def test_bounded_retries_recovers_flaky_stage(self, db_session):
        flaky = FlakyStage()
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[flaky],
            max_retries=2,
            retry_delay_seconds=0.01,
        )
        result = pipeline.execute()

        assert result.status == PipelineStatus.SUCCESS
        assert result.stages["flaky_stage"].status == StageStatus.SUCCESS
        assert result.stages["flaky_stage"].retries_attempted == 1

    def test_dry_run_does_not_persist_scrape_run(self, db_session):
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[StageA()],
        )
        result = pipeline.execute(dry_run=True)

        assert result.is_dry_run is True
        assert result.run_id is None
        assert result.status == PipelineStatus.SUCCESS

    def test_stage_filtering(self, db_session):
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[StageA(), StageB()],
        )
        result = pipeline.execute(stage_filter="stage_a")

        assert len(result.stages) == 1
        assert "stage_a" in result.stages
        assert "stage_b" not in result.stages

    def test_app_monitor_lazy_imports_and_attributes(self):
        import app.monitor as monitor
        from app.monitor import BaseStage as LazyBaseStage
        from app.monitor import MonitorPipeline as LazyMonitorPipeline
        from app.monitor import MonitorRunner as LazyMonitorRunner

        assert LazyMonitorPipeline is MonitorPipeline
        assert LazyBaseStage is BaseStage
        assert issubclass(LazyMonitorRunner, object)

        with pytest.raises(AttributeError, match="has no attribute 'NonExistent'"):
            _ = monitor.NonExistent

