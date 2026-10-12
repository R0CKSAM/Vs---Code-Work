"""
test_notification_deduplication.py – Unit tests for Phase 9 NotificationDeduplicator.
"""

from __future__ import annotations

import pytest
from app.database.connection import utc_now
from app.database.models import ChangeEvent, NotificationBatch
from app.notifications.deduplicator import NotificationDeduplicator


class TestNotificationDeduplication:
    def test_filter_unnotified_events_skips_already_notified(self, db_session):
        # Seed 1 unnotified and 1 already notified event in DB
        e1 = ChangeEvent(
            entity_type="MATCH",
            entity_id=1,
            change_type="CREATED",
            new_value="Match 1",
            detected_at=utc_now(),
            notified_at=None,
        )
        e2 = ChangeEvent(
            entity_type="MATCH",
            entity_id=2,
            change_type="CREATED",
            new_value="Match 2",
            detected_at=utc_now(),
            notified_at=utc_now(),
        )
        db_session.add_all([e1, e2])
        db_session.commit()

        dedup = NotificationDeduplicator(db_session)
        unnotified = dedup.filter_unnotified_events([e1, e2])
        assert len(unnotified) == 1
        assert unnotified[0].id == e1.id

    def test_batch_already_sent_detection(self, db_session):
        batch = NotificationBatch(
            batch_key="test-key-12345",
            subject="Test Alert",
            status="SENT",
            event_count=2,
            recipient_count=1,
            sent_at=utc_now(),
        )
        db_session.add(batch)
        db_session.commit()

        dedup = NotificationDeduplicator(db_session)
        assert dedup.is_batch_already_sent("test-key-12345") is True
        assert dedup.is_batch_already_sent("unknown-key-999") is False

    def test_failed_batch_is_not_considered_already_sent(self, db_session):
        batch = NotificationBatch(
            batch_key="failed-key-67890",
            subject="Failed Alert",
            status="FAILED",
            event_count=1,
            recipient_count=1,
            error_message="SMTP connection timed out",
        )
        db_session.add(batch)
        db_session.commit()

        dedup = NotificationDeduplicator(db_session)
        # Failed batch must allow retry, so is_batch_already_sent is False
        assert dedup.is_batch_already_sent("failed-key-67890") is False
