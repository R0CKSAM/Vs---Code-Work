"""
test_notification_service.py – Unit tests for Phase 9 NotificationService execution and lifecycle.
"""

from __future__ import annotations

import pytest
from app.database.connection import utc_now
from app.database.models import ChangeEvent
from app.notifications.email_backend import TestEmailBackend
from app.notifications.models import EmailRecipientConfig, NotificationStatus
from app.notifications.service import NotificationService


@pytest.fixture
def recipient_cfg():
    return EmailRecipientConfig(
        from_addr="alerts@fancode.local",
        to_addrs=["admin@fancode.local"],
    )


class TestNotificationService:
    def test_full_successful_notification_pipeline(self, db_session, recipient_cfg):
        # 1. Seed unnotified ChangeEvent in DB
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=101,
            external_id="101",
            change_type="STATUS_CHANGED",
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity="CRITICAL",
            source_url="https://www.fancode.com/match/101",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend, recipients=recipient_cfg)

        # 2. Run service
        result = service.run()

        assert result.events_inspected >= 1
        assert result.events_eligible >= 1
        assert result.batches_created == 1
        assert result.emails_sent == 1
        assert len(backend.sent_messages) == 1
        assert "LIVE" in backend.sent_messages[0].subject

        # 3. Check DB audit state
        db_session.refresh(event)
        assert event.notified_at is not None

    def test_dry_run_does_not_send_or_mark_notified(self, db_session, recipient_cfg):
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=102,
            external_id="102",
            change_type="CREATED",
            new_value="Arsenal vs Chelsea",
            severity="IMPORTANT",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend, recipients=recipient_cfg)

        result = service.run(dry_run=True)

        assert result.is_dry_run is True
        assert result.batches_created == 1
        assert result.emails_sent == 0
        assert len(backend.sent_messages) == 0

        # Event remains unnotified
        db_session.refresh(event)
        assert event.notified_at is None

    def test_repeated_run_does_not_resend_notified_event(self, db_session, recipient_cfg):
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=103,
            external_id="103",
            change_type="STATUS_CHANGED",
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity="CRITICAL",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend, recipients=recipient_cfg)

        # Run 1: Sends email
        res1 = service.run()
        assert res1.emails_sent == 1
        assert len(backend.sent_messages) == 1

        # Run 2: Exact same state -> deduplicated, 0 new emails sent
        backend.clear()
        res2 = service.run()
        assert res2.emails_sent == 0
        assert len(backend.sent_messages) == 0

    def test_failed_delivery_records_failure_and_allows_retry(self, db_session, recipient_cfg):
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=104,
            external_id="104",
            change_type="STATUS_CHANGED",
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity="CRITICAL",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        # Run 1: Simulated delivery failure
        failing_backend = TestEmailBackend(should_fail=True, fail_message="SMTP down")
        service1 = NotificationService(session=db_session, backend=failing_backend, recipients=recipient_cfg)

        res1 = service1.run()
        assert res1.deliveries_failed == 1
        assert res1.emails_sent == 0

        # Event is NOT marked notified
        db_session.refresh(event)
        assert event.notified_at is None

        # Run 2: Retry with healthy backend succeeds
        working_backend = TestEmailBackend(should_fail=False)
        service2 = NotificationService(session=db_session, backend=working_backend, recipients=recipient_cfg)

        res2 = service2.run()
        assert res2.emails_sent == 1
        assert len(working_backend.sent_messages) == 1

        # Now event IS marked notified
        db_session.refresh(event)
        assert event.notified_at is not None

    def test_no_email_sent_on_empty_events(self, db_session, recipient_cfg):
        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend, recipients=recipient_cfg)

        result = service.run()
        assert result.events_inspected == 0
        assert result.batches_created == 0
        assert result.emails_sent == 0
        assert len(backend.sent_messages) == 0
