"""
test_notification_repository.py – Unit tests for NotificationRepository and audit persistence (Phase 9).
"""

from __future__ import annotations

import pytest
from app.database.connection import utc_now
from app.database.models import ChangeEvent
from app.notifications.repository import NotificationRepository


class TestNotificationRepository:
    def test_create_batch_and_retrieve(self, db_session):
        repo = NotificationRepository(db_session)
        batch = repo.create_batch(
            batch_key="bkey-101",
            subject="Test Batch Subject",
            event_count=2,
            recipient_count=1,
            status="PENDING",
        )
        assert batch.id is not None
        assert batch.status == "PENDING"

        retrieved = repo.get_batch_by_key("bkey-101")
        assert retrieved is not None
        assert retrieved.id == batch.id
        assert retrieved.subject == "Test Batch Subject"

    def test_link_events_to_batch(self, db_session):
        repo = NotificationRepository(db_session)
        ev1 = ChangeEvent(
            entity_type="MATCH",
            entity_id=101,
            change_type="CREATED",
            new_value="Match A",
            detected_at=utc_now(),
        )
        ev2 = ChangeEvent(
            entity_type="VIDEO",
            entity_id=201,
            change_type="CREATED",
            new_value="Video A",
            detected_at=utc_now(),
        )
        db_session.add_all([ev1, ev2])
        db_session.commit()

        batch = repo.create_batch(batch_key="bkey-link-test", subject="Link Test", event_count=2)
        repo.link_events_to_batch(batch.id, [ev1.id, ev2.id])

        assert len(batch.event_links) == 2
        linked_eids = {link.change_event_id for link in batch.event_links}
        assert linked_eids == {ev1.id, ev2.id}

    def test_record_delivery_and_mark_batch_status(self, db_session):
        repo = NotificationRepository(db_session)
        batch = repo.create_batch(batch_key="bkey-delivery-test", subject="Delivery Test")

        delivery = repo.record_delivery(
            batch_id=batch.id,
            recipient="admin@fancode.local",
            status="SENT",
            provider="test",
        )
        assert delivery.id is not None
        assert delivery.status == "SENT"

        repo.mark_batch_sent(batch.id)
        assert batch.status == "SENT"
        assert batch.sent_at is not None

        repo.mark_batch_failed(batch.id, error_message="Connection timed out")
        assert batch.status == "FAILED"
        assert batch.error_message == "Connection timed out"

    def test_mark_events_notified_and_filter(self, db_session):
        repo = NotificationRepository(db_session)
        ev1 = ChangeEvent(
            entity_type="MATCH",
            entity_id=1,
            change_type="CREATED",
            new_value="Match 1",
            severity="IMPORTANT",
            detected_at=utc_now(),
        )
        ev2 = ChangeEvent(
            entity_type="MATCH",
            entity_id=2,
            change_type="STATUS_CHANGED",
            new_value="LIVE",
            severity="CRITICAL",
            detected_at=utc_now(),
        )
        db_session.add_all([ev1, ev2])
        db_session.commit()

        unnotified = repo.get_unnotified_events()
        assert len(unnotified) >= 2

        count = repo.mark_events_notified([ev1.id])
        assert count == 1

        unnotified_after = repo.get_unnotified_events()
        assert any(e.id == ev2.id for e in unnotified_after)
        assert not any(e.id == ev1.id for e in unnotified_after)
