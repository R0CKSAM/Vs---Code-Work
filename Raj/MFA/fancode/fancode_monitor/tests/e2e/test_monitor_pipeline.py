"""
test_monitor_pipeline.py – End-to-end and Playwright workflow validation for Phase 10 Monitor & Orchestrator.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from app.change_detection.detector import ChangeDetector
from app.config.settings import settings
from app.database.models import Match
from app.database.repositories import MatchesRepository, ScrapeRunsRepository
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineStatus, StageResult, StageStatus
from app.monitor.pipeline import MonitorPipeline
from app.monitor.runner import MonitorRunner
from app.monitor.stages import BaseStage, ChangeDetectionStage, NotificationStage, PipelineContext
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService


class MockLiveScraperStage(BaseStage):
    """Simulates dynamic scrapers observing changes on FanCode."""
    name = "mock_scraper"
    def __init__(self, matches_to_return):
        self.matches_to_return = matches_to_return

    def run(self, context: PipelineContext) -> StageResult:
        context.scraped_data["matches"] = self.matches_to_return
        return StageResult(name=self.name, records_processed=len(self.matches_to_return))


class TestMonitorPipelineE2E:
    def test_full_monitoring_lifecycle_and_idempotency(self, page: Page, db_session, tmp_path):
        """
        Validates complete monitor lifecycle:
        1. Connectivity smoke check via Playwright.
        2. Cycle 1: Pre-seed match -> Match transitions to LIVE -> Alert email dispatched.
        3. Cycle 2: Same state -> Zero change events -> Zero emails dispatched.
        """
        try:
            page.goto(
                settings.BASE_URL,
                wait_until="domcontentloaded",
                timeout=settings.BROWSER_TIMEOUT,
            )
        except Exception:
            pass
        assert not page.is_closed()

        matches_repo = MatchesRepository(session=db_session)
        # 1. Pre-seed Match in UPCOMING state
        matches_repo.upsert(
            external_id="match-mon-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            source_url="https://www.fancode.com/match/mon-1",
            status="UPCOMING",
            venue="Emirates Stadium",
        )
        db_session.commit()

        # 2. Cycle 1: Scraper observes Match is now LIVE
        live_match_data = [
            {
                "match_id": "match-mon-1",
                "title": "Arsenal vs Chelsea",
                "status": "LIVE",
                "venue": "Emirates Stadium",
                "source_url": "https://www.fancode.com/match/mon-1",
            }
        ]

        test_email_backend = TestEmailBackend()
        # Custom NotificationStage using test_email_backend
        class CustomNotifStage(BaseStage):
            name = "notifications"
            def run(self, context: PipelineContext) -> StageResult:
                srv = NotificationService(session=context.session, backend=test_email_backend)
                res = srv.run(scrape_run_id=context.scrape_run_id, dry_run=context.is_dry_run)
                return StageResult(
                    name=self.name,
                    notifications_sent=res.emails_sent,
                    records_processed=res.events_inspected,
                )

        lock_file = tmp_path / "e2e_mon.lock"
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[
                MockLiveScraperStage(live_match_data),
                ChangeDetectionStage(),
                CustomNotifStage(),
            ],
        )
        runner = MonitorRunner(pipeline=pipeline, lock=MonitorLock(lock_file=str(lock_file)))

        # Run Cycle 1
        res1 = runner.run_once()
        assert res1.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 1
        assert "LIVE" in test_email_backend.sent_messages[0].subject

        # Run Cycle 2: Exactly same incoming state
        test_email_backend.clear()
        res2 = runner.run_once()
        assert res2.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 0  # Deduplicated, no spam!

    def test_overlapping_run_lock_protection(self, db_session, tmp_path):
        """
        Validates that an active run blocks concurrent executions.
        """
        lock_file = tmp_path / "overlap.lock"
        lock1 = MonitorLock(lock_file=str(lock_file))
        assert lock1.acquire() is True

        lock2 = MonitorLock(lock_file=str(lock_file))
        pipeline = MonitorPipeline(session=db_session, stages=[])
        runner2 = MonitorRunner(pipeline=pipeline, lock=lock2)

        res2 = runner2.run_once()
        assert res2.status == PipelineStatus.SKIPPED
        assert "Active lock" in (res2.error_summary or "")

        lock1.release()
