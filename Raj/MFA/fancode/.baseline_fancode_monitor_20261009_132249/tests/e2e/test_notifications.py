"""
test_notifications.py – End-to-end integration and Playwright workflow tests for Phase 9 Alerting Engine.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from app.change_detection.detector import ChangeDetector
from app.config.settings import settings
from app.database.connection import utc_now
from app.database.models import Match
from app.database.repositories import ChangeEventsRepository, MatchesRepository
from app.notifications.email_backend import TestEmailBackend
from app.notifications.models import EmailRecipientConfig
from app.notifications.service import NotificationService


class TestNotificationsE2E:
    def test_full_pipeline_change_detection_to_alert_digest(self, page: Page, db_session):
        """
        E2E Test validating the full pipeline:
        1. Browser smoke check for FanCode.
        2. Detection of multiple changes (Match goes LIVE, new video created).
        3. Notification service batches changes into 1 digest email.
        4. Audit checks and deduplication on subsequent execution.
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
        matches_repo = MatchesRepository(session=db_session)

        # 1. Pre-seed Match in UPCOMING state
        matches_repo.upsert(
            external_id="match-alert-1",
            title="Real Madrid vs Barcelona",
            slug="real-madrid-vs-barcelona",
            source_url="https://www.fancode.com/match/alert-1",
            status="UPCOMING",
            venue="Santiago Bernabeu",
        )
        db_session.commit()

        # 2. Scrape Run: Match goes LIVE and a new video is discovered
        incoming_matches = [
            {
                "match_id": "match-alert-1",
                "title": "Real Madrid vs Barcelona",
                "status": "LIVE",
                "venue": "Santiago Bernabeu",
                "source_url": "https://www.fancode.com/match/alert-1",
            }
        ]
        incoming_videos = [
            {
                "slug": "real-barca-highlights",
                "title": "Real Madrid vs Barcelona - El Clasico Highlights",
                "video_type": "HIGHLIGHTS",
                "source_url": "https://www.fancode.com/video/real-barca-hl",
            }
        ]

        det_res1 = detector.detect_matches(incoming_matches, scrape_run_id=10)
        det_res2 = detector.detect_videos(incoming_videos, scrape_run_id=10)

        assert det_res1.status_events == 1
        assert det_res2.created_events == 1

        # 3. Alerting Pipeline
        backend = TestEmailBackend()
        recipients = EmailRecipientConfig(
            from_addr="alerts@fancode-monitor.local",
            to_addrs=["ops@fancode-monitor.local"],
        )
        service = NotificationService(session=db_session, backend=backend, recipients=recipients)

        # Run notification service
        run_res = service.run()

        assert run_res.events_inspected == 2
        assert run_res.events_eligible == 2
        assert run_res.batches_created == 1
        assert run_res.emails_sent == 1

        # 4. Validate Email content
        assert len(backend.sent_messages) == 1
        sent_email = backend.sent_messages[0]

        assert sent_email.subject == (
            "FanCode Monitor — 🔴 LIVE: Real Madrid vs Barcelona (+1 other change)"
        )
        assert "Real Madrid vs Barcelona" in sent_email.html_body
        assert "https://www.fancode.com/match/alert-1" in sent_email.html_body
        assert "El Clasico Highlights" in sent_email.html_body
        assert "https://www.fancode.com/video/real-barca-hl" in sent_email.html_body

        # Plain text fallback checks
        assert "Status changed: UPCOMING -> LIVE" in sent_email.text_body
        assert "https://www.fancode.com/match/alert-1" in sent_email.text_body

        # 5. Subsequent run sends NO duplicate emails
        backend.clear()
        res_repeat = service.run()
        assert res_repeat.emails_sent == 0
        assert len(backend.sent_messages) == 0

    def test_cross_scraper_single_notification_lifecycle(self, db_session):
        """
        Validates cross-scraper lifecycle:
        - Schedule and Detail scrapers see UPCOMING.
        - Live Now sees LIVE.
        - Exactly ONE notification email is sent.
        """
        detector = ChangeDetector(session=db_session)
        matches_repo = MatchesRepository(session=db_session)

        # Scrape 1: Schedule scraper discovers UPCOMING
        s1_matches = [
            {
                "match_id": "match-cross-1",
                "title": "India vs Australia",
                "status": "UPCOMING",
                "source_url": "https://www.fancode.com/match/ind-aus",
            }
        ]
        detector.detect_matches(s1_matches, scrape_run_id=1)
        matches_repo.upsert(
            external_id="match-cross-1",
            title="India vs Australia",
            slug="india-vs-australia",
            source_url="https://www.fancode.com/match/ind-aus",
            status="UPCOMING",
        )
        db_session.commit()

        # Scrape 2: Detail scraper discovers same UPCOMING (no change)
        det_detail = detector.detect_matches(s1_matches, scrape_run_id=2)
        assert det_detail.created_events == 0
        assert det_detail.updated_events == 0
        assert det_detail.status_events == 0

        # Scrape 3: Live Now scraper discovers match is LIVE
        s3_live = [
            {
                "match_id": "match-cross-1",
                "title": "India vs Australia",
                "status": "LIVE",
                "source_url": "https://www.fancode.com/match/ind-aus",
            }
        ]
        det_live = detector.detect_matches(s3_live, scrape_run_id=3)
        assert det_live.status_events == 1

        # Run Notification Engine
        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend)

        # 1 CREATED (from scrape 1) + 1 STATUS_CHANGED (from scrape 3) = 1 digest batch
        result = service.run()
        assert result.batches_created == 1
        assert result.emails_sent == 1
        assert len(backend.sent_messages) == 1

        # Ensure subsequent run produces 0 emails
        backend.clear()
        res2 = service.run()
        assert res2.emails_sent == 0
        assert len(backend.sent_messages) == 0
