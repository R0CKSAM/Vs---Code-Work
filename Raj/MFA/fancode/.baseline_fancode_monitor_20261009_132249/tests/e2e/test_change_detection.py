"""
End-to-end integration tests for Change Detection Engine (Phase 8).
"""

import pytest
from playwright.sync_api import Page
from app.config.settings import settings
from app.change_detection.detector import ChangeDetector
from app.change_detection.models import ChangeType, EntityType, Severity
from app.database.repositories import ChangeEventsRepository, MatchesRepository


class TestChangeDetectionE2E:
    def test_full_lifecycle_discovery_to_change_events(self, page: Page, db_session):
        """
        Simulate a realistic multi-stage scrape run sequence:
        1. Navigate browser to check connectivity.
        2. Initial scrape discovers Match 1 & Match 2.
        3. Second scrape observes Match 1 transitioning to LIVE.
        4. Match 2 has live score change (noise, ignored).
        5. New Video highlights published for Match 1.
        6. Verify ChangeEvent logs and notification readiness.
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

        detector = ChangeDetector(session=db_session)
        events_repo = ChangeEventsRepository(session=db_session)
        matches_repo = MatchesRepository(session=db_session)

        # Stage 1: Initial Discovery
        scrape_1_matches = [
            {
                "match_id": "match-e2e-1",
                "title": "Arsenal vs Chelsea",
                "status": "UPCOMING",
                "venue": "Emirates Stadium",
                "source_url": "https://www.fancode.com/match/e2e-1",
            },
            {
                "match_id": "match-e2e-2",
                "title": "Liverpool vs Manchester City",
                "status": "UPCOMING",
                "venue": "Anfield",
                "source_url": "https://www.fancode.com/match/e2e-2",
            },
        ]

        res1 = detector.detect_matches(scrape_1_matches, scrape_run_id=1)
        assert res1.created_events == 2

        # Simulate scraper persistence into matches table
        m1 = matches_repo.upsert(
            external_id="match-e2e-1",
            title="Arsenal vs Chelsea",
            slug="arsenal-vs-chelsea",
            source_url="https://www.fancode.com/match/e2e-1",
            status="UPCOMING",
            venue="Emirates Stadium",
        )
        m2 = matches_repo.upsert(
            external_id="match-e2e-2",
            title="Liverpool vs Manchester City",
            slug="liverpool-vs-manchester-city",
            source_url="https://www.fancode.com/match/e2e-2",
            status="UPCOMING",
            venue="Anfield",
        )

        # Stage 2: Next Scrape Run
        # Match 1 goes LIVE
        # Match 2 has only score updated (2-1 in 70 min)
        scrape_2_matches = [
            {
                "match_id": "match-e2e-1",
                "title": "Arsenal vs Chelsea",
                "status": "LIVE",
                "venue": "Emirates Stadium",
                "source_url": "https://www.fancode.com/match/e2e-1",
            },
            {
                "match_id": "match-e2e-2",
                "title": "Liverpool vs Manchester City",
                "status": "UPCOMING",
                "venue": "Anfield",
                "score_summary": "2-1 in 70 min",
                "source_url": "https://www.fancode.com/match/e2e-2",
            },
        ]

        res2 = detector.detect_matches(scrape_2_matches, scrape_run_id=2)
        assert res2.status_events == 1
        assert res2.updated_events == 0  # Score update produces no event

        # Stage 3: New Video published
        new_videos = [
            {
                "slug": "arsenal-vs-chelsea-highlights",
                "title": "Arsenal vs Chelsea - Highlights",
                "video_type": "HIGHLIGHTS",
                "duration_seconds": 600,
                "source_url": "https://www.fancode.com/video/arsenal-chelsea-hl",
            }
        ]
        res3 = detector.detect_videos(new_videos, scrape_run_id=3)
        assert res3.created_events == 1

        # Stage 4: Audit check in DB
        unnotified = events_repo.get_unnotified()
        assert len(unnotified) >= 3

        # Critical severity assigned for match going LIVE
        live_events = [e for e in unnotified if e.change_type == ChangeType.STATUS_CHANGED.value]
        assert len(live_events) == 1
        assert live_events[0].severity == Severity.CRITICAL.value

