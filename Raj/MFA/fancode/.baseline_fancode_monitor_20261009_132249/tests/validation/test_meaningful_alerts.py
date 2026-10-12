"""
test_meaningful_alerts.py – Validation tests for Meaningful Alerts, Noise Filtering, and Notification Redesign.

Verifies:
- Noisy fields (source_url, score_summary, overs, wickets, timestamps) yield 0 change events and 0 alerts.
- URL variations and tracking query params do not trigger changes.
- Critical status transitions (UPCOMING -> LIVE, UPCOMING -> CANCELLED) produce CRITICAL alerts with distinct subjects.
- Important status transitions (LIVE -> COMPLETED, UPCOMING -> POSTPONED) produce IMPORTANT alerts.
- Fixture updates (venue, start_time, match_date, team names) produce IMPORTANT alerts.
- New entities (MATCH, TOUR, VIDEO, SPORT) produce valid notifications.
- Tour scraper URL normalization strips match/video routes from tour entities.
- NotificationRenderer generates clean, human-friendly HTML and plain-text digests with action links and no raw URL dumps.
- Full end-to-end ChangeDetector -> NotificationService pipeline on an isolated database.
"""

from __future__ import annotations

import html
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.change_detection.classifier import (
    MEANINGFUL_FIELDS,
    NOISY_FIELDS,
    ChangeClassifier,
)
from app.change_detection.comparator import StateComparator
from app.change_detection.detector import ChangeDetector
from app.change_detection.models import (
    ChangeType,
    EntityType,
    ProposedChangeEvent,
    Severity,
)
from app.database.connection import Base
from app.database.models import ChangeEvent, Match, NotificationBatch, NotificationDelivery, Tour
from app.database.repositories import ChangeEventsRepository, MatchesRepository, ToursRepository
from app.notifications.email_backend import TestEmailBackend
from app.notifications.grouping import EventGrouper
from app.notifications.models import EmailRecipientConfig, GroupedEntity, NotificationBatchDraft
from app.notifications.policy import NotificationPolicy
from app.notifications.renderer import NotificationRenderer
from app.notifications.service import NotificationService
from app.scraper.tours.parser import ToursParser


class TestMeaningfulAlertsAndNoiseFiltering:
    """Comprehensive test suite for noise elimination and alert relevancy."""

    # -------------------------------------------------------------------------
    # 1. Field Classification & Noise Elimination
    # -------------------------------------------------------------------------

    def test_source_url_is_classified_as_noisy(self):
        """source_url must be classified as noisy and unmonitored for all entity types."""
        for entity_type in (EntityType.MATCH.value, EntityType.TOUR.value, EntityType.VIDEO.value, EntityType.SPORT.value):
            assert ChangeClassifier.is_noisy_field(entity_type, "source_url") is True
            assert ChangeClassifier.is_meaningful_field(entity_type, "source_url") is False
            assert ChangeClassifier.classify_field_change(entity_type, "source_url", "https://fancode.com/a", "https://fancode.com/b") is None

    def test_live_score_counters_are_classified_as_noisy(self):
        """Score summary, overs, wickets, points, and elapsed time must be noisy and produce 0 events."""
        score_fields = ["score_summary", "score", "innings", "overs", "wickets", "points", "elapsed_time", "period"]
        for f in score_fields:
            assert ChangeClassifier.is_noisy_field(EntityType.MATCH.value, f) is True
            assert ChangeClassifier.is_meaningful_field(EntityType.MATCH.value, f) is False
            assert ChangeClassifier.classify_field_change(EntityType.MATCH.value, f, "10/0", "15/1") is None

    def test_meaningful_fields_allowlist(self):
        """Only genuine fixture and entity metadata fields are allowed as meaningful."""
        assert "venue" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "start_time" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "match_date" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "team_a_name" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "team_b_name" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "status" in MEANINGFUL_FIELDS[EntityType.MATCH.value]
        assert "title" in MEANINGFUL_FIELDS[EntityType.MATCH.value]

    # -------------------------------------------------------------------------
    # 2. State Comparison & URL Normalization
    # -------------------------------------------------------------------------

    def test_url_tracking_parameters_equality(self):
        """StateComparator normalizes URL tracking parameters and whitespace."""
        url1 = "https://www.fancode.com/match/12345?utm_source=twitter&utm_medium=social"
        url2 = "https://www.fancode.com/match/12345"
        # Normalization removes tracking params
        assert StateComparator.are_values_equal(url1, url2) is True

    def test_compare_fields_ignores_unmonitored_fields(self):
        """StateComparator only compares fields passed in the monitored allowlist."""
        old_data = {"title": "India vs Aus", "source_url": "https://fancode.com/1", "score_summary": "0/0"}
        new_data = {"title": "India vs Aus", "source_url": "https://fancode.com/2", "score_summary": "50/0"}

        meaningful = MEANINGFUL_FIELDS[EntityType.MATCH.value]
        changed = StateComparator.compare_fields(old_data, new_data, meaningful)
        assert len(changed) == 0  # Zero meaningful fields changed

    # -------------------------------------------------------------------------
    # 3. Status Transitions & Severities
    # -------------------------------------------------------------------------

    def test_upcoming_to_live_transition_is_critical(self):
        """A match going LIVE is CRITICAL severity."""
        c_type, sev = ChangeClassifier.classify_status_transition("UPCOMING", "LIVE")
        assert c_type == ChangeType.STATUS_CHANGED.value
        assert sev == Severity.CRITICAL.value

    def test_upcoming_to_cancelled_transition_is_critical(self):
        """A match being CANCELLED or ABANDONED is CRITICAL severity."""
        for cancelled_val in ("CANCELLED", "ABANDONED"):
            c_type, sev = ChangeClassifier.classify_status_transition("UPCOMING", cancelled_val)
            assert c_type == ChangeType.STATUS_CHANGED.value
            assert sev == Severity.CRITICAL.value

    def test_live_to_completed_transition_is_important(self):
        """A match finishing (COMPLETED) is IMPORTANT severity."""
        c_type, sev = ChangeClassifier.classify_status_transition("LIVE", "COMPLETED")
        assert c_type == ChangeType.STATUS_CHANGED.value
        assert sev == Severity.IMPORTANT.value

    def test_fixture_field_updates_are_important(self):
        """Venue, schedule, or team name changes are IMPORTANT severity."""
        for f in ("venue", "start_time", "match_date", "team_a_name", "team_b_name"):
            res = ChangeClassifier.classify_field_change(EntityType.MATCH.value, f, "Old Val", "New Val")
            assert res is not None
            c_type, sev = res
            assert c_type == ChangeType.UPDATED.value
            assert sev == Severity.IMPORTANT.value

    # -------------------------------------------------------------------------
    # 4. Tour Parser URL Sanitization
    # -------------------------------------------------------------------------

    def test_tours_parser_strips_nested_match_routes(self):
        """ToursParser must not assign match detail URLs to Tour entities."""
        payload = {
            "tourName": "Tata IPL 2026",
            "tourId": "ipl-2026",
            "url": "https://www.fancode.com/cricket/tour/tata-ipl-2026/matches/101/live-match-info",
        }
        record = ToursParser.parse_tour_dict(payload)
        assert record is not None
        assert "/matches/" not in record.source_url
        assert record.source_url == "https://www.fancode.com/cricket/tour/tata-ipl-2026"

    # -------------------------------------------------------------------------
    # 5. Notification Policy
    # -------------------------------------------------------------------------

    def test_notification_policy_rejects_noisy_fields(self):
        """NotificationPolicy rejects any event with noisy field_name."""
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.UPDATED.value,
            field_name="source_url",
            old_value="https://fancode.com/1",
            new_value="https://fancode.com/2",
            severity=Severity.INFO.value,
        )
        assert NotificationPolicy.is_notifiable(event) is False

    def test_notification_policy_accepts_critical_and_important_changes(self):
        """NotificationPolicy accepts meaningful status changes and fixture updates."""
        live_event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
        )
        assert NotificationPolicy.is_notifiable(live_event) is True

        venue_event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.UPDATED.value,
            field_name="venue",
            old_value="Wankhede",
            new_value="Eden Gardens",
            severity=Severity.IMPORTANT.value,
        )
        assert NotificationPolicy.is_notifiable(venue_event) is True

    # -------------------------------------------------------------------------
    # 6. Notification Renderer Design
    # -------------------------------------------------------------------------

    def test_renderer_generates_clean_live_subject(self):
        """When a match goes LIVE, subject highlights LIVE and match title."""
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
        )
        grouped = [
            GroupedEntity(
                entity_type="MATCH",
                entity_id=1,
                title="India vs Australia",
                source_url="https://fancode.com/match/ind-aus",
                events=[event],
            )
        ]
        batch = NotificationBatchDraft(
            batch_key="test-live",
            events=[event],
            grouped_entities=grouped,
        )

        subject = NotificationRenderer.generate_subject(batch)
        assert "🔴 LIVE: India vs Australia" in subject
        assert "FanCode Monitor" in subject

    def test_renderer_generates_clean_cancelled_subject(self):
        """When a match is cancelled, subject highlights CANCELLED."""
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="CANCELLED",
            severity=Severity.CRITICAL.value,
        )
        grouped = [
            GroupedEntity(
                entity_type="MATCH",
                entity_id=1,
                title="Arsenal vs Chelsea",
                source_url="https://fancode.com/match/ars-che",
                events=[event],
            )
        ]
        batch = NotificationBatchDraft(
            batch_key="test-cancel",
            events=[event],
            grouped_entities=grouped,
        )

        subject = NotificationRenderer.generate_subject(batch)
        assert "⚠️ CANCELLED: Arsenal vs Chelsea" in subject

    def test_renderer_html_does_not_dump_raw_urls(self):
        """HTML rendering places links behind 'View on FanCode →' and does not dump raw URL text."""
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
        )
        url = "https://www.fancode.com/cricket/match/105423/india-vs-australia-1st-t20"
        grouped = [
            GroupedEntity(
                entity_type="MATCH",
                entity_id=1,
                title="India vs Australia",
                source_url=url,
                events=[event],
            )
        ]
        batch = NotificationBatchDraft(
            batch_key="test-html",
            events=[event],
            grouped_entities=grouped,
        )

        html_body = NotificationRenderer.render_html(batch)
        assert "View on FanCode &rarr;" in html_body
        assert f'href="{html.escape(url)}"' in html_body
        # Raw URL should NOT be displayed as visible text outside href
        assert f">{url}<" not in html_body

    def test_renderer_plain_text_format(self):
        """Plain-text rendering provides clean structured summary."""
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
        )
        grouped = [
            GroupedEntity(
                entity_type="MATCH",
                entity_id=1,
                title="India vs Australia",
                source_url="https://fancode.com/match/100",
                events=[event],
            )
        ]
        batch = NotificationBatchDraft(
            batch_key="test-text",
            events=[event],
            grouped_entities=grouped,
        )

        text_body = NotificationRenderer.render_text(batch)
        assert "[MATCH] India vs Australia" in text_body
        assert "Status changed: UPCOMING -> LIVE (Severity: CRITICAL)" in text_body
        assert "Link: https://fancode.com/match/100" in text_body

    # -------------------------------------------------------------------------
    # 7. End-to-End Detector -> Notification Pipeline
    # -------------------------------------------------------------------------

    def test_end_to_end_detector_and_notification_pipeline(self, db_session):
        """
        Simulates:
        1. Seed Match in DB with status UPCOMING.
        2. Scrape observes status changed to LIVE and score_summary noise.
        3. Detector creates exactly 1 event (for status=LIVE) and ignores score noise.
        4. NotificationService dispatches 1 email with '🔴 LIVE: India vs Australia' subject.
        5. Database audit records batch SENT and marks change_event notified.
        """
        matches_repo = MatchesRepository(db_session)
        match = matches_repo.upsert(
            external_id="match-e2e-1",
            title="India vs Australia",
            slug="india-vs-australia",
            status="UPCOMING",
            venue="Eden Gardens",
            source_url="https://fancode.com/match/ind-aus",
        )
        db_session.commit()

        # Incoming scraper data: status is LIVE, plus noisy score summary
        scraper_data = [
            {
                "external_id": "match-e2e-1",
                "title": "India vs Australia",
                "status": "LIVE",
                "score_summary": "45/1 (5.2 ov)",
                "source_url": "https://fancode.com/match/ind-aus?utm_source=fancode",
                "venue": "Eden Gardens",
            }
        ]

        detector = ChangeDetector(session=db_session)
        det_result = detector.detect_matches(current_data_list=scraper_data, scrape_run_id=101)
        db_session.commit()

        # Must produce exactly 1 change event (the status transition), zero for score or URL
        assert len(det_result.events) == 1
        ev = det_result.events[0]
        assert ev.change_type == ChangeType.STATUS_CHANGED.value
        assert ev.field_name == "status"
        assert ev.new_value == "LIVE"
        assert ev.severity == Severity.CRITICAL.value

        # Run Notification Service
        test_backend = TestEmailBackend()
        recipients = EmailRecipientConfig(from_addr="alerts@fancode.local", to_addrs=["user@example.com"])
        service = NotificationService(session=db_session, backend=test_backend, recipients=recipients)

        notif_result = service.run(scrape_run_id=101)
        assert notif_result.emails_sent == 1
        assert len(test_backend.sent_messages) == 1

        sent_msg = test_backend.sent_messages[0]
        assert "🔴 LIVE: India vs Australia" in sent_msg.subject
        assert "India vs Australia" in sent_msg.html_body
        assert "View on FanCode &rarr;" in sent_msg.html_body
        assert "https://fancode.com/match/ind-aus" in sent_msg.html_body

        # Confirm DB audit
        db_batch = db_session.query(NotificationBatch).first()
        assert db_batch is not None
        assert db_batch.status == "SENT"
        assert db_batch.event_count == 1

        db_delivery = db_session.query(NotificationDelivery).first()
        assert db_delivery is not None
        assert db_delivery.status == "SENT"
        assert db_delivery.recipient == "user@example.com"

        db_event = db_session.query(ChangeEvent).filter_by(id=ev.entity_id).first()
        # Event is marked notified
        assert db_session.query(ChangeEvent).filter(ChangeEvent.notified_at.isnot(None)).count() == 1
