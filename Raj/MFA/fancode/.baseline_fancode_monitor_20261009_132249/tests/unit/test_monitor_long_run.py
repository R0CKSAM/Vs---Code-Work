"""
test_monitor_long_run.py – Multi-cycle deterministic monitoring test (Phase 11).

Simulates 6 monitoring cycles:
- Cycle 1: CREATED
- Cycle 2: Unchanged (idempotency check)
- Cycle 3: Meaningful UPDATE (venue change)
- Cycle 4: Unchanged (idempotency check)
- Cycle 5: STATUS_CHANGED (to LIVE)
- Cycle 6: Unchanged (idempotency check)

Verifies:
- Accurate change event persistence
- Accurate notification dispatching
- Zero duplicate change events or spam emails
- Healthy operational health state
- Zero false removals
"""

from __future__ import annotations

import pytest
from app.database.models import ChangeEvent
from app.monitor.health import MonitorHealth
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineStatus, StageResult
from app.monitor.pipeline import MonitorPipeline
from app.monitor.runner import MonitorRunner
from app.monitor.stages import BaseStage, ChangeDetectionStage, PipelineContext
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService


class DynamicMockScraperStage(BaseStage):
    """Dynamic scraper stage returning custom payload per cycle."""
    name = "mock_scraper"
    requires_browser = False

    def __init__(self):
        self.payload = []

    def set_payload(self, data):
        self.payload = data

    def run(self, context: PipelineContext) -> StageResult:
        context.scraped_data["matches"] = self.payload
        return StageResult(name=self.name, records_processed=len(self.payload))


class TestMonitorLongRunSimulation:
    def test_multi_cycle_monitoring_lifecycle(self, db_session, tmp_path):
        scraper_stage = DynamicMockScraperStage()
        test_email_backend = TestEmailBackend()

        class CustomNotificationStage(BaseStage):
            name = "notifications"
            requires_browser = False

            def run(self, context: PipelineContext) -> StageResult:
                srv = NotificationService(session=context.session, backend=test_email_backend)
                res = srv.run(scrape_run_id=context.scrape_run_id, dry_run=context.is_dry_run)
                if not context.is_dry_run:
                    from app.database.repositories import MatchesRepository
                    from app.scraper.schedule.normalizer import derive_slug
                    repo = MatchesRepository(session=context.session)
                    for item in scraper_stage.payload:
                        title = item.get("title") or "Match"
                        slug = item.get("slug") or derive_slug(title)
                        repo.upsert(
                            external_id=item.get("match_id") or item.get("external_id"),
                            title=title,
                            slug=slug,
                            status=item.get("status"),
                            venue=item.get("venue"),
                            source_url=item.get("source_url") or f"https://www.fancode.com/match/{slug}",
                        )
                    context.session.commit()
                return StageResult(
                    name=self.name,
                    notifications_sent=res.emails_sent,
                    records_processed=res.events_inspected,
                )

        lock_file = tmp_path / "long_run.lock"
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[
                scraper_stage,
                ChangeDetectionStage(),
                CustomNotificationStage(),
            ],
        )
        runner = MonitorRunner(pipeline=pipeline, lock=MonitorLock(lock_file=str(lock_file)))

        # -------------------------------------------------------------
        # Cycle 1: Match CREATED
        # -------------------------------------------------------------
        c1_data = [
            {
                "match_id": "match-lr-100",
                "title": "Arsenal vs Chelsea",
                "status": "UPCOMING",
                "venue": "Emirates Stadium",
                "source_url": "https://www.fancode.com/match/lr-100",
            }
        ]
        scraper_stage.set_payload(c1_data)
        test_email_backend.clear()

        res1 = runner.run_once()
        assert res1.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 1
        msg1 = test_email_backend.sent_messages[0]
        assert msg1.subject == "FanCode Monitor — NEW Match: Arsenal vs Chelsea"
        assert "Arsenal vs Chelsea" in msg1.text_body or "Arsenal vs Chelsea" in msg1.html_body
        assert "CREATED" in msg1.text_body or "UPCOMING" in msg1.text_body

        # -------------------------------------------------------------
        # Cycle 2: Exactly identical state (Unchanged)
        # -------------------------------------------------------------
        test_email_backend.clear()
        res2 = runner.run_once()
        assert res2.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 0  # No duplicate notifications!

        # -------------------------------------------------------------
        # Cycle 3: Meaningful UPDATE (Venue rescheduled)
        # -------------------------------------------------------------
        c3_data = [
            {
                "match_id": "match-lr-100",
                "title": "Arsenal vs Chelsea",
                "status": "UPCOMING",
                "venue": "Wembley Stadium",  # Changed venue
                "source_url": "https://www.fancode.com/match/lr-100",
            }
        ]
        scraper_stage.set_payload(c3_data)
        test_email_backend.clear()

        res3 = runner.run_once()
        assert res3.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 1
        msg3 = test_email_backend.sent_messages[0]
        assert msg3.subject == "FanCode Monitor — Venue Changed: Arsenal vs Chelsea"
        assert "UPDATED" in msg3.text_body or "Wembley Stadium" in msg3.text_body

        # -------------------------------------------------------------
        # Cycle 4: Exactly identical state (Unchanged)
        # -------------------------------------------------------------
        test_email_backend.clear()
        res4 = runner.run_once()
        assert res4.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 0

        # -------------------------------------------------------------
        # Cycle 5: STATUS_CHANGED (Transition to LIVE)
        # -------------------------------------------------------------
        c5_data = [
            {
                "match_id": "match-lr-100",
                "title": "Arsenal vs Chelsea",
                "status": "LIVE",  # Status transition!
                "venue": "Wembley Stadium",
                "source_url": "https://www.fancode.com/match/lr-100",
            }
        ]
        scraper_stage.set_payload(c5_data)
        test_email_backend.clear()

        res5 = runner.run_once()
        assert res5.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 1
        msg5 = test_email_backend.sent_messages[0]
        assert msg5.subject == "FanCode Monitor — 🔴 LIVE: Arsenal vs Chelsea"
        assert "LIVE" in msg5.text_body or "STATUS_CHANGED" in msg5.text_body

        # -------------------------------------------------------------
        # Cycle 6: Exactly identical state (Unchanged)
        # -------------------------------------------------------------
        test_email_backend.clear()
        res6 = runner.run_once()
        assert res6.status == PipelineStatus.SUCCESS
        assert len(test_email_backend.sent_messages) == 0

        # Verify change event history: exactly 3 events recorded, zero REMOVED events
        events = list(db_session.query(ChangeEvent).filter(ChangeEvent.external_id == "match-lr-100").all())
        assert len(events) == 3
        change_types = {e.change_type for e in events}
        assert "REMOVED" not in change_types
        assert "CREATED" in change_types
        assert "UPDATED" in change_types
        assert "STATUS_CHANGED" in change_types

        # Verify system health status
        health_status = MonitorHealth.get_status(session=db_session)
        assert health_status["health"] == "HEALTHY"
        assert health_status["database"] == "ok"
