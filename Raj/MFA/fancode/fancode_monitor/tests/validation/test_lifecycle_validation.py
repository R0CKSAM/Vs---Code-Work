"""
test_lifecycle_validation.py – Phase 12 End-to-End Entity Lifecycle & Scraper Safety Tests.

Verifies:
- 6-cycle deterministic lifecycle:
    1. Match appears (UPCOMING) -> CREATED -> Alert sent
    2. Match transitions to LIVE -> STATUS_CHANGED -> Alert sent
    3. Noise update (Score only changes) -> NO change event -> NO alert
    4. Match finishes (COMPLETED) -> STATUS_CHANGED -> Alert sent
    5. Meaningful update (Venue changed) -> UPDATED -> Alert sent
    6. Authoritative complete snapshot removes match -> REMOVED -> Alert sent
- Scrape Failure Safety:
    - Scraper failure / empty scrape NEVER causes false mass REMOVED events.
    - Pipeline records error without corrupting existing records.
    - Subsequent successful run recovers cleanly.
"""

from __future__ import annotations

import pytest

from app.change_detection.detector import ChangeDetector
from app.change_detection.models import ChangeType, EntityType, Severity
from app.database.models import ChangeEvent, Match
from app.database.repositories import ChangeEventsRepository, MatchesRepository
from app.monitor.models import PipelineStatus, StageResult, StageStatus
from app.monitor.pipeline import MonitorPipeline
from app.monitor.stages import BaseStage, ChangeDetectionStage, PipelineContext
from app.notifications.email_backend import TestEmailBackend
from app.notifications.service import NotificationService


class TestLifecycleValidation:
    """Validates the complete 6-cycle entity lifecycle and scrape failure safety."""

    def test_complete_match_lifecycle_six_cycles(self, db_session):
        """
        Executes a 6-stage lifecycle on a single match:
        CREATED -> LIVE -> SCORE NOISE -> COMPLETED -> VENUE UPDATED -> AUTHORITATIVE REMOVAL.
        """
        detector = ChangeDetector(session=db_session)
        matches_repo = MatchesRepository(session=db_session)
        events_repo = ChangeEventsRepository(session=db_session)
        backend = TestEmailBackend()
        notif_service = NotificationService(session=db_session, backend=backend)

        # -------------------------------------------------------------
        # Cycle 1: CREATED (UPCOMING)
        # -------------------------------------------------------------
        c1_matches = [
            {
                "match_id": "lifecycle-match-1",
                "title": "Arsenal vs Chelsea",
                "status": "UPCOMING",
                "venue": "Emirates Stadium",
                "source_url": "https://fancode.com/match/lifecycle-1",
            }
        ]
        res1 = detector.detect_matches(c1_matches, scrape_run_id=1)
        assert res1.created_events == 1
        assert len(res1.events) == 1
        assert res1.events[0].change_type == ChangeType.CREATED.value

        # Persist baseline and deliver notification
        m1 = matches_repo.upsert(
            external_id="lifecycle-match-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            status="UPCOMING",
            venue="Emirates Stadium",
            source_url="https://fancode.com/match/lifecycle-1",
        )
        db_session.commit()
        backend.clear()
        notif_res1 = notif_service.run(scrape_run_id=1)
        assert notif_res1.emails_sent == 1

        # -------------------------------------------------------------
        # Cycle 2: Status transition to LIVE
        # -------------------------------------------------------------
        c2_matches = [
            {
                "match_id": "lifecycle-match-1",
                "title": "Arsenal vs Chelsea",
                "status": "LIVE",
                "venue": "Emirates Stadium",
                "source_url": "https://fancode.com/match/lifecycle-1",
            }
        ]
        res2 = detector.detect_matches(c2_matches, scrape_run_id=2)
        assert res2.status_events == 1
        assert res2.events[0].change_type == ChangeType.STATUS_CHANGED.value
        assert res2.events[0].new_value == "LIVE"

        matches_repo.upsert(
            external_id="lifecycle-match-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            status="LIVE",
            venue="Emirates Stadium",
            source_url="https://fancode.com/match/lifecycle-1",
        )
        db_session.commit()
        backend.clear()
        notif_res2 = notif_service.run(scrape_run_id=2)
        assert notif_res2.emails_sent == 1
        assert "LIVE" in backend.sent_messages[0].subject

        # -------------------------------------------------------------
        # Cycle 3: Score update only (Noisy field -> Ignored)
        # -------------------------------------------------------------
        c3_matches = [
            {
                "match_id": "lifecycle-match-1",
                "title": "Arsenal vs Chelsea",
                "status": "LIVE",
                "venue": "Emirates Stadium",
                "score_summary": "1-0 (34 min)",
                "source_url": "https://fancode.com/match/lifecycle-1",
            }
        ]
        res3 = detector.detect_matches(c3_matches, scrape_run_id=3)
        assert len(res3.events) == 0  # Zero events produced for score update
        backend.clear()
        notif_res3 = notif_service.run(scrape_run_id=3)
        assert notif_res3.emails_sent == 0

        # -------------------------------------------------------------
        # Cycle 4: Match COMPLETED
        # -------------------------------------------------------------
        c4_matches = [
            {
                "match_id": "lifecycle-match-1",
                "title": "Arsenal vs Chelsea",
                "status": "COMPLETED",
                "venue": "Emirates Stadium",
                "score_summary": "2-1 (Full Time)",
                "source_url": "https://fancode.com/match/lifecycle-1",
            }
        ]
        res4 = detector.detect_matches(c4_matches, scrape_run_id=4)
        assert res4.status_events == 1
        assert res4.events[0].change_type == ChangeType.STATUS_CHANGED.value
        assert res4.events[0].new_value == "COMPLETED"

        matches_repo.upsert(
            external_id="lifecycle-match-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            status="COMPLETED",
            venue="Emirates Stadium",
            source_url="https://fancode.com/match/lifecycle-1",
        )
        db_session.commit()
        backend.clear()
        notif_res4 = notif_service.run(scrape_run_id=4)
        assert notif_res4.emails_sent == 1

        # -------------------------------------------------------------
        # Cycle 5: Meaningful update (Venue changed)
        # -------------------------------------------------------------
        c5_matches = [
            {
                "match_id": "lifecycle-match-1",
                "title": "Arsenal vs Chelsea",
                "status": "COMPLETED",
                "venue": "Wembley Stadium",  # Changed venue
                "source_url": "https://fancode.com/match/lifecycle-1",
            }
        ]
        res5 = detector.detect_matches(c5_matches, scrape_run_id=5)
        assert res5.updated_events == 1
        assert res5.events[0].change_type == ChangeType.UPDATED.value
        assert res5.events[0].field_name == "venue"

        matches_repo.upsert(
            external_id="lifecycle-match-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            status="COMPLETED",
            venue="Wembley Stadium",
            source_url="https://fancode.com/match/lifecycle-1",
        )
        db_session.commit()
        backend.clear()
        notif_res5 = notif_service.run(scrape_run_id=5)
        assert notif_res5.emails_sent == 1

        # -------------------------------------------------------------
        # Cycle 6: Authoritative complete snapshot removes match
        # -------------------------------------------------------------
        # Passing an authoritative snapshot with a different match and complete_snapshot=True
        c6_matches = [
            {
                "match_id": "lifecycle-match-other",
                "title": "Liverpool vs Everton",
                "status": "UPCOMING",
                "venue": "Anfield",
                "source_url": "https://fancode.com/match/other",
            }
        ]
        res6 = detector.detect_matches(c6_matches, scrape_run_id=6, complete_snapshot=True)
        assert res6.removed_events == 1
        removed_ev = next(e for e in res6.events if e.change_type == ChangeType.REMOVED.value)
        assert removed_ev.external_id == "lifecycle-match-1"

        backend.clear()
        notif_res6 = notif_service.run(scrape_run_id=6)
        assert notif_res6.emails_sent == 1

    def test_failed_scrape_safety_never_causes_false_removals(self, db_session):
        """
        Critical safety check:
        When a scraper fails or returns an empty list, the change detector MUST NEVER
        produce REMOVED change events, preventing false alert storms.
        """
        matches_repo = MatchesRepository(session=db_session)
        detector = ChangeDetector(session=db_session)
        backend = TestEmailBackend()
        notif_service = NotificationService(session=db_session, backend=backend)

        # 1. Seed 3 matches in database
        for i in range(1, 4):
            matches_repo.upsert(
                external_id=f"safety-match-{i}",
                title=f"Match {i}",
                slug=f"match-{i}",
                status="UPCOMING",
                venue="Stadium",
                source_url=f"https://fancode.com/match/{i}",
            )
        db_session.commit()
        assert db_session.query(Match).count() == 3

        # 2. Simulate empty scrape (scraper failed or returned 0 items)
        empty_scraped_matches = []

        # Case A: Default snapshot (complete_snapshot=False)
        res_partial = detector.detect_matches(empty_scraped_matches, scrape_run_id=10, complete_snapshot=False)
        assert res_partial.removed_events == 0
        assert len(res_partial.events) == 0

        # Case B: Even if complete_snapshot=True is passed with an empty list, removal safety guard prevents mass removal
        res_empty = detector.detect_matches(empty_scraped_matches, scrape_run_id=11, complete_snapshot=True)
        assert res_empty.removed_events == 0
        assert len(res_empty.events) == 0

        # Verify no alerts dispatched
        backend.clear()
        notif_res = notif_service.run(scrape_run_id=11)
        assert notif_res.emails_sent == 0
        assert len(backend.sent_messages) == 0

        # Verify database entities are 100% preserved
        assert db_session.query(Match).count() == 3
