"""
test_notification_policy.py – Unit tests for Phase 9 NotificationPolicy.
"""

from __future__ import annotations

import pytest
from app.change_detection.models import ChangeType, EntityType, ProposedChangeEvent, Severity
from app.notifications.policy import NotificationPolicy
from tests.fixtures.notifications import (
    SAMPLE_EVENT_MATCH_CANCELLED,
    SAMPLE_EVENT_MATCH_CREATED,
    SAMPLE_EVENT_MATCH_LIVE,
    SAMPLE_EVENT_MATCH_POSTPONED,
    SAMPLE_EVENT_MATCH_REMOVED,
    SAMPLE_EVENT_MATCH_VENUE_CHANGED,
    SAMPLE_EVENT_NOISY_SCORE,
    SAMPLE_EVENT_SPORT_CREATED,
    SAMPLE_EVENT_TOUR_CREATED,
    SAMPLE_EVENT_VIDEO_CREATED,
)


class TestNotificationPolicy:
    def test_created_match_is_notifiable(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=1,
            change_type=ChangeType.CREATED.value,
            new_value="Arsenal vs Chelsea",
            severity=Severity.IMPORTANT.value,
        )
        assert NotificationPolicy.is_notifiable(event) is True

    def test_created_video_is_notifiable(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.VIDEO.value,
            entity_id=2,
            change_type=ChangeType.CREATED.value,
            new_value="Match Highlights",
            severity=Severity.INFO.value,
        )
        assert NotificationPolicy.is_notifiable(event) is True

    def test_important_event_is_notifiable(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=3,
            change_type=ChangeType.UPDATED.value,
            field_name="venue",
            old_value="Old Venue",
            new_value="New Venue",
            severity=Severity.IMPORTANT.value,
        )
        assert NotificationPolicy.is_notifiable(event) is True

    def test_critical_event_is_notifiable(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=4,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
        )
        assert NotificationPolicy.is_notifiable(event) is True

    def test_low_severity_event_is_ignored(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=5,
            change_type=ChangeType.UPDATED.value,
            field_name="stream_url",
            severity="LOW",
        )
        assert NotificationPolicy.is_notifiable(event) is False

    def test_noisy_score_field_is_ignored(self):
        event = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=6,
            change_type=ChangeType.UPDATED.value,
            field_name="score_summary",
            old_value="120/3",
            new_value="121/3",
            severity=Severity.INFO.value,
        )
        assert NotificationPolicy.is_notifiable(event) is False

    def test_filter_events_applies_policy(self):
        events = [
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=1,
                change_type=ChangeType.CREATED.value,
                severity=Severity.IMPORTANT.value,
            ),
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=2,
                change_type=ChangeType.UPDATED.value,
                field_name="score_summary",
                severity="LOW",
            ),
        ]
        filtered = NotificationPolicy.filter_events(events)
        assert len(filtered) == 1
        assert filtered[0].entity_id == 1
