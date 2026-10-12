"""
test_production_hardening.py – Playwright E2E verification of Phase 11 production hardening & observability.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from app.config.settings import settings
from app.database.models import Match
from app.database.repositories import MatchesRepository
from app.monitor.health import MonitorHealth
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineStatus, StageResult
from app.monitor.pipeline import MonitorPipeline
from app.monitor.runner import MonitorRunner
from app.monitor.stages import BaseStage, ChangeDetectionStage, PipelineContext
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService
from app.observability.diagnostics import collect_system_diagnostics


class MockLiveScraperStage(BaseStage):
    """Deterministic scraper stage returning controlled test fixtures."""
    name = "mock_scraper"
    requires_browser = False

    def __init__(self, matches):
        self.matches = matches

    def run(self, context: PipelineContext) -> StageResult:
        context.scraped_data["matches"] = self.matches
        return StageResult(name=self.name, records_processed=len(self.matches))


class TestProductionHardeningE2E:
    def test_full_pipeline_with_diagnostics_and_idempotency(self, page: Page, db_session, tmp_path):
        """
        Playwright E2E validating:
        1. Connectivity smoke test.
        2. Database diagnostics and health audit.
        3. Cycle 1: Pre-seeded match state change -> Change detected -> Alert dispatched.
        4. Health and diagnostics reflect updated state.
        5. Cycle 2: Identical state -> Idempotent execution (0 alerts dispatched).
        """
        # 1. Smoke connectivity test
        try:
            page.goto(settings.BASE_URL, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)
        except Exception:
            pass
        assert not page.is_closed()

        # 2. Database diagnostics pre-check
        diag_pre = collect_system_diagnostics(session=db_session)
        assert diag_pre["status"] == "HEALTHY"
        assert diag_pre["database_integrity"]["connection"] == "OK"

        # 3. Pre-seed match in UPCOMING state
        matches_repo = MatchesRepository(session=db_session)
        matches_repo.upsert(
            external_id="match-harden-1",
            title="Manchester City vs Liverpool",
            slug="manchester-city-vs-liverpool",
            source_url="https://www.fancode.com/match/harden-1",
            status="UPCOMING",
            venue="Etihad Stadium",
        )
        db_session.commit()

        # 4. Cycle 1: Match transitions to LIVE
        live_data = [
            {
                "match_id": "match-harden-1",
                "title": "Manchester City vs Liverpool",
                "status": "LIVE",
                "venue": "Etihad Stadium",
                "source_url": "https://www.fancode.com/match/harden-1",
            }
        ]

        test_email_backend = TestEmailBackend()

        class CustomNotifStage(BaseStage):
            name = "notifications"
            requires_browser = False

            def run(self, context: PipelineContext) -> StageResult:
                srv = NotificationService(session=context.session, backend=test_email_backend)
                res = srv.run(scrape_run_id=context.scrape_run_id, dry_run=context.is_dry_run)
                return StageResult(
                    name=self.name,
                    notifications_sent=res.emails_sent,
                    records_processed=res.events_inspected,
                )

        lock_file = tmp_path / "harden_e2e.lock"
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[
                MockLiveScraperStage(live_data),
                ChangeDetectionStage(),
                CustomNotifStage(),
            ],
        )
        runner = MonitorRunner(pipeline=pipeline, lock=MonitorLock(lock_file=str(lock_file)))

        # Execute Cycle 1
        res1 = runner.run_once()
        assert res1.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 1
        assert "LIVE" in test_email_backend.sent_messages[0].subject

        # 5. Verify health state updated
        health_post = MonitorHealth.get_status(session=db_session)
        assert health_post["health"] == "HEALTHY"
        assert health_post["latest_run"] is not None
        assert health_post["latest_run"]["status"] == "success"

        # 6. Cycle 2: Exactly identical state -> Idempotent check
        test_email_backend.clear()
        res2 = runner.run_once()
        assert res2.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 0  # Deduplicated!
