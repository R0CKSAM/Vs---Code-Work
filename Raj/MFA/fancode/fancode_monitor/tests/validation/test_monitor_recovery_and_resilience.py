"""
test_monitor_recovery_and_resilience.py – Phase 12 Monitor Recovery & Multi-Cycle Resilience Tests.

Verifies:
- Stale monitor lock recovery when previous process terminates abnormally.
- Active lock protection blocks concurrent pipeline execution.
- Stale run reclamation reconciles interrupted scrape runs.
- 10-Cycle deterministic long-run simulation covering:
    * New entities
    * Idempotent unchanged states
    * Status transitions (UPCOMING -> LIVE -> COMPLETED)
    * Noise updates (score updates ignored)
    * Transient scraper failure (no false removals, safe recovery)
    * Meaningful updates (venue change)
    * New entity additions
- Zero duplicate entities, zero duplicate change events, zero spam alerts.
- Operational database integrity and health status verification.
"""

from __future__ import annotations

from datetime import timedelta
import json
import os
import time
import pytest

from app.database.connection import utc_now
from app.database.models import ChangeEvent, Match, ScrapeRun
from app.database.repositories import MatchesRepository, ScrapeRunsRepository
from app.maintenance.stale_runs import reclaim_stale_runs
from app.monitor.health import MonitorHealth
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineStatus, StageResult
from app.monitor.pipeline import MonitorPipeline
from app.monitor.runner import MonitorRunner
from app.monitor.stages import BaseStage, ChangeDetectionStage, PipelineContext
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService
from app.observability.diagnostics import check_database_integrity


class DynamicResilienceScraperStage(BaseStage):
    """Configurable mock scraper stage that allows switching payloads or simulating failure."""
    name = "mock_scraper"
    requires_browser = False

    def __init__(self):
        self.payload = []
        self.should_fail = False

    def set_payload(self, data):
        self.payload = data
        self.should_fail = False

    def trigger_failure(self):
        self.should_fail = True

    def run(self, context: PipelineContext) -> StageResult:
        if self.should_fail:
            raise ConnectionResetError("Simulated scraper network timeout")
        context.scraped_data["matches"] = self.payload
        return StageResult(name=self.name, records_processed=len(self.payload))


class TestMonitorRecoveryAndResilienceValidation:
    """Validates monitor restart recovery, stale lock handling, and multi-cycle simulation."""

    def test_stale_lock_recovery_after_process_termination(self, tmp_path):
        """Verifies that an abandoned lock file from an extinct PID is safely reclaimed."""
        lock_file = tmp_path / "abandoned.lock"
        # Write fake lock info with dead PID and expired timestamp
        dead_pid = 99999999  # Guaranteed non-existent PID
        payload = {
            "pid": dead_pid,
            "started_at": time.time() - 7200,
            "host": "test-host",
            "ttl": 3600,
        }
        lock_file.write_text(json.dumps(payload), encoding="utf-8")

        lock = MonitorLock(lock_file=str(lock_file), timeout_seconds=3600)
        # An abandoned/dead-PID lock is stale, so is_locked() correctly reports False (no valid active lock)
        assert lock.is_locked() is False
        assert lock_file.exists() is True

        # Acquire must detect the stale lock, reclaim it, and become active
        acquired = lock.acquire()
        assert acquired is True
        assert lock.is_locked() is True

        # Clean release
        lock.release()
        assert lock.is_locked() is False

    def test_active_lock_blocks_concurrent_execution(self, db_session, tmp_path):
        """Verifies an active held lock blocks a concurrent runner with SKIPPED status."""
        lock_file = tmp_path / "active.lock"
        lock1 = MonitorLock(lock_file=str(lock_file))
        assert lock1.acquire() is True

        lock2 = MonitorLock(lock_file=str(lock_file))
        pipeline = MonitorPipeline(session=db_session, stages=[])
        runner2 = MonitorRunner(pipeline=pipeline, lock=lock2)

        res = runner2.run_once()
        assert res.status == PipelineStatus.SKIPPED
        assert "Active lock" in (res.error_summary or "")

        lock1.release()

    def test_stale_run_reclamation_and_resumption(self, db_session):
        """Verifies that an interrupted scrape run marked 'running' past threshold is reclaimed to 'stale_reclaimed'."""
        stale_time = utc_now() - timedelta(hours=2)
        interrupted_run = ScrapeRun(
            run_type="monitor",
            status="running",
            started_at=stale_time,
            metadata_json={"pid": 99999999},  # non-existent dead PID
        )
        db_session.add(interrupted_run)
        db_session.commit()

        # Execute stale run reclamation
        reclaimed_ids = reclaim_stale_runs(session=db_session, timeout_seconds=1800)
        assert len(reclaimed_ids) >= 1
        assert interrupted_run.id in reclaimed_ids

        db_session.refresh(interrupted_run)
        assert interrupted_run.status == "stale_reclaimed"
        assert "reclaimed" in (interrupted_run.error_message or "").lower()

    def test_ten_cycle_deterministic_monitoring_lifecycle(self, db_session, tmp_path):
        """
        Executes a 10-cycle deterministic monitoring test:
        - Cycle 1: Discovery (Match A, UPCOMING) -> Alert 1
        - Cycle 2: Identical state -> 0 alerts
        - Cycle 3: Match A goes LIVE -> Alert 2
        - Cycle 4: Score noise only -> 0 alerts
        - Cycle 5: Scraper failure (non-fatal recovery) -> 0 false removals -> 0 alerts
        - Cycle 6: Match A venue update -> Alert 3
        - Cycle 7: Identical state -> 0 alerts
        - Cycle 8: Match A COMPLETED -> Alert 4
        - Cycle 9: New Match B appears -> Alert 5
        - Cycle 10: Final identical state -> 0 alerts
        """
        scraper_stage = DynamicResilienceScraperStage()
        email_backend = TestEmailBackend()

        class PostDetectionNotificationAndPersistStage(BaseStage):
            name = "notifications"
            requires_browser = False

            def run(self, context: PipelineContext) -> StageResult:
                srv = NotificationService(session=context.session, backend=email_backend)
                res = srv.run(scrape_run_id=context.scrape_run_id, dry_run=context.is_dry_run)
                if not context.is_dry_run and not scraper_stage.should_fail:
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
                            source_url=item.get("source_url") or f"https://fancode.com/match/{slug}",
                        )
                    context.session.commit()
                return StageResult(
                    name=self.name,
                    notifications_sent=res.emails_sent,
                    records_processed=res.events_inspected,
                )

        lock_file = tmp_path / "ten_cycle.lock"
        pipeline = MonitorPipeline(
            session=db_session,
            stages=[
                scraper_stage,
                ChangeDetectionStage(),
                PostDetectionNotificationAndPersistStage(),
            ],
        )
        runner = MonitorRunner(pipeline=pipeline, lock=MonitorLock(lock_file=str(lock_file)))

        match_a_base = {
            "match_id": "match-resilience-10",
            "title": "Arsenal vs Chelsea",
            "status": "UPCOMING",
            "venue": "Emirates Stadium",
            "source_url": "https://fancode.com/match/resilience-10",
        }

        # Cycle 1: CREATED
        scraper_stage.set_payload([match_a_base])
        email_backend.clear()
        r1 = runner.run_once()
        assert r1.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 1

        # Cycle 2: Identical
        email_backend.clear()
        r2 = runner.run_once()
        assert r2.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 0

        # Cycle 3: Goes LIVE
        match_a_live = dict(match_a_base, status="LIVE")
        scraper_stage.set_payload([match_a_live])
        email_backend.clear()
        r3 = runner.run_once()
        assert r3.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 1

        # Cycle 4: Score noise
        match_a_noise = dict(match_a_live, score_summary="1-0 (25 min)")
        scraper_stage.set_payload([match_a_noise])
        email_backend.clear()
        r4 = runner.run_once()
        assert r4.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 0

        # Cycle 5: Scraper failure
        scraper_stage.trigger_failure()
        email_backend.clear()
        r5 = runner.run_once()
        # Pipeline status captures non-fatal stage failure safely
        assert r5.status in (PipelineStatus.PARTIAL, PipelineStatus.FAILED)
        assert len(email_backend.sent_messages) == 0
        # Critical: Match A is still in DB (zero false removals)
        assert db_session.query(Match).filter_by(external_id="match-resilience-10").first() is not None

        # Cycle 6: Match A venue update
        match_a_venue = dict(match_a_live, venue="Wembley Stadium")
        scraper_stage.set_payload([match_a_venue])
        email_backend.clear()
        r6 = runner.run_once()
        assert r6.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 1

        # Cycle 7: Identical
        email_backend.clear()
        r7 = runner.run_once()
        assert r7.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 0

        # Cycle 8: Match A COMPLETED
        match_a_done = dict(match_a_venue, status="COMPLETED")
        scraper_stage.set_payload([match_a_done])
        email_backend.clear()
        r8 = runner.run_once()
        assert r8.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 1

        # Cycle 9: New Match B appears
        match_b = {
            "match_id": "match-resilience-20",
            "title": "Liverpool vs Man City",
            "status": "UPCOMING",
            "venue": "Anfield",
            "source_url": "https://fancode.com/match/resilience-20",
        }
        scraper_stage.set_payload([match_a_done, match_b])
        email_backend.clear()
        r9 = runner.run_once()
        assert r9.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 1

        # Cycle 10: Identical final state
        email_backend.clear()
        r10 = runner.run_once()
        assert r10.status == PipelineStatus.SUCCESS
        assert len(email_backend.sent_messages) == 0

        # Final Verification
        db_audit = check_database_integrity(db_session)
        assert db_audit["status"] == "OK"

        health = MonitorHealth.get_status(session=db_session)
        assert health["database"] == "ok"
        assert health["health"] in ("HEALTHY", "DEGRADED")
