"""
test_monitor_stages.py – Unit tests for Stage abstractions and execution handling (Phase 10).
"""

from __future__ import annotations

import pytest
from app.change_detection.models import ChangeType, EntityType
from app.database.connection import utc_now
from app.database.models import ChangeEvent
from app.monitor.models import StageResult, StageStatus
from app.monitor.stages import (
    BaseStage,
    ChangeDetectionStage,
    NotificationStage,
    PipelineContext,
)


class MockSuccessStage(BaseStage):
    name = "mock_success"
    def run(self, context: PipelineContext) -> StageResult:
        return StageResult(name=self.name, records_processed=5)


class MockFailingStage(BaseStage):
    name = "mock_fail"
    def run(self, context: PipelineContext) -> StageResult:
        raise ValueError("Simulated stage error")


class TestMonitorStages:
    def test_base_stage_success_execution(self, db_session):
        context = PipelineContext(session=db_session)
        stage = MockSuccessStage()
        result = stage.execute(context)

        assert result.name == "mock_success"
        assert result.status == StageStatus.SUCCESS
        assert result.records_processed == 5
        assert result.duration_seconds >= 0.0
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_base_stage_failure_capture(self, db_session):
        context = PipelineContext(session=db_session)
        stage = MockFailingStage()
        result = stage.execute(context)

        assert result.name == "mock_fail"
        assert result.status == StageStatus.FAILED
        assert len(result.errors) == 1
        assert "Simulated stage error" in result.errors[0]

    def test_change_detection_stage_execution(self, db_session):
        context = PipelineContext(
            session=db_session,
            scraped_data={
                "matches": [
                    {
                        "external_id": "match-mstage-1",
                        "title": "Arsenal vs Chelsea",
                        "status": "UPCOMING",
                        "source_url": "https://www.fancode.com/match/mstage-1",
                    }
                ]
            },
        )
        stage = ChangeDetectionStage()
        result = stage.execute(context)

        assert result.status == StageStatus.SUCCESS
        assert result.records_processed == 1
        assert result.records_created == 1

    def test_notification_stage_execution(self, db_session):
        # Seed an unnotified change event
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=99,
            change_type="CREATED",
            new_value="Sample Match",
            severity="IMPORTANT",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        context = PipelineContext(session=db_session, is_dry_run=True)
        stage = NotificationStage()
        result = stage.execute(context)

        assert result.status == StageStatus.SUCCESS
        assert result.records_processed >= 1

    def test_schedule_stage_with_real_schedule_match_contract(self, monkeypatch, db_session):
        from unittest.mock import MagicMock
        from app.monitor.stages import ScheduleStage
        from app.scraper.schedule.models import ScheduleMatch

        sample_match = ScheduleMatch(
            title="India vs Australia",
            source_url="https://www.fancode.com/match/101",
            external_id="match-101",
            status="UPCOMING",
            venue="Wankhede Stadium",
            start_time="19:00",
            team_a_name="India",
            team_b_name="Australia",
            score_summary=None,
        )

        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = [sample_match]

        monkeypatch.setattr("app.monitor.stages.FanCodeScheduleScraper", lambda browser: mock_scraper)

        mock_browser = MagicMock()
        context = PipelineContext(session=db_session, browser=mock_browser, is_dry_run=True)
        stage = ScheduleStage()
        result = stage.execute(context)

        assert result.status == StageStatus.SUCCESS
        assert result.records_processed == 1
        assert "matches" in context.scraped_data
        assert context.scraped_data["matches"][0]["external_id"] == "match-101"
        assert context.scraped_data["matches"][0]["title"] == "India vs Australia"
        assert context.scraped_data["matches"][0]["team_a_name"] == "India"

    def test_match_detail_stage_with_enrich_batch_contract(self, monkeypatch, db_session):
        from unittest.mock import MagicMock
        from app.monitor.stages import MatchDetailStage
        from app.scraper.match_detail.models import MatchDetail

        sample_detail = MatchDetail(
            match_external_id="match-101",
            title="India vs Australia",
            source_url="https://www.fancode.com/match/101",
            venue="Wankhede Stadium",
        )

        mock_scraper = MagicMock()
        mock_scraper.enrich_batch.return_value = [sample_detail]

        monkeypatch.setattr("app.monitor.stages.FanCodeMatchDetailScraper", lambda browser: mock_scraper)

        mock_browser = MagicMock()
        context = PipelineContext(session=db_session, browser=mock_browser, is_dry_run=True)
        stage = MatchDetailStage()
        result = stage.execute(context)

        assert result.status == StageStatus.SUCCESS
        assert result.records_processed == 1
        mock_scraper.enrich_batch.assert_called_once_with(limit=20, persist_db=False)

    def test_match_detail_stage_empty_batch_succeeds(self, monkeypatch, db_session):
        from unittest.mock import MagicMock
        from app.monitor.stages import MatchDetailStage

        mock_scraper = MagicMock()
        mock_scraper.enrich_batch.return_value = []

        monkeypatch.setattr("app.monitor.stages.FanCodeMatchDetailScraper", lambda browser: mock_scraper)

        mock_browser = MagicMock()
        context = PipelineContext(session=db_session, browser=mock_browser, is_dry_run=False)
        stage = MatchDetailStage()
        result = stage.execute(context)

        assert result.status == StageStatus.SUCCESS
        assert result.records_processed == 0

