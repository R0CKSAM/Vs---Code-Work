"""
test_notification_idempotency_validation.py – Phase 12 Notification Idempotency & Delivery Resilience Tests.

Verifies:
- Repeated notification dispatching is strictly idempotent (zero duplicate alerts).
- Failed delivery allows retry while successful delivery permanently marks events notified.
- Dry-run mode never sends emails or mutates database notified timestamps.
- Console, Test, and SMTP backend configurations execute safely.
- Deterministic batch grouping ensures identical digest structures.
"""

from __future__ import annotations

import pytest

from app.database.connection import utc_now
from app.database.models import ChangeEvent, NotificationBatch, NotificationDelivery
from app.database.repositories import ChangeEventsRepository
from app.notifications.email_backend import ConsoleEmailBackend, TestEmailBackend
from app.notifications.grouping import EventGrouper
from app.notifications.models import EmailRecipientConfig
from app.notifications.policy import NotificationPolicy
from app.notifications.service import NotificationService
from app.notifications.smtp_backend import SmtpEmailBackend


class TestNotificationIdempotencyValidation:
    """Validates alerting idempotency, delivery retries, and backend isolation."""

    @pytest.fixture
    def test_recipients(self):
        return EmailRecipientConfig(
            from_addr="alerts@fancode.local",
            to_addrs=["admin@fancode.local"],
        )

    def test_repeated_run_does_not_resend_or_duplicate(self, db_session, test_recipients):
        """Validates that running notification service back-to-back produces exactly 1 send."""
        # 1. Create a fresh change event
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=101,
            external_id="match-idemp-1",
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
        service = NotificationService(session=db_session, backend=backend, recipients=test_recipients)

        # 2. Run 1: Must send 1 email
        res1 = service.run()
        assert res1.emails_sent == 1
        assert len(backend.sent_messages) == 1

        db_session.refresh(event)
        assert event.notified_at is not None

        # 3. Run 2: Same state, must send 0 emails
        res2 = service.run()
        assert res2.emails_sent == 0
        assert len(backend.sent_messages) == 1  # No additional message appended

        # 4. Run 3: Even with explicit scrape_run_id, must not resend
        res3 = service.run(scrape_run_id=event.scrape_run_id)
        assert res3.emails_sent == 0
        assert len(backend.sent_messages) == 1

    def test_failed_delivery_allows_retry_and_succeeds(self, db_session, test_recipients):
        """Validates failure isolation: an error in delivery does not mark events notified, allowing retry."""
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=102,
            external_id="match-idemp-2",
            change_type="CREATED",
            new_value="Madrid vs Barcelona",
            severity="IMPORTANT",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        # Run with failing backend
        failing_backend = TestEmailBackend(should_fail=True)
        service_failing = NotificationService(session=db_session, backend=failing_backend, recipients=test_recipients)
        res_fail = service_failing.run()

        assert res_fail.emails_sent == 0
        assert res_fail.deliveries_failed >= 1

        # Event must NOT be marked notified yet
        db_session.refresh(event)
        assert event.notified_at is None

        # Retry with healthy backend
        healthy_backend = TestEmailBackend(should_fail=False)
        service_healthy = NotificationService(session=db_session, backend=healthy_backend, recipients=test_recipients)
        res_retry = service_healthy.run()

        assert res_retry.emails_sent == 1
        assert len(healthy_backend.sent_messages) == 1

        # Event is now marked notified
        db_session.refresh(event)
        assert event.notified_at is not None

    def test_dry_run_never_dispatches_or_mutates_state(self, db_session, test_recipients):
        """Validates dry-run guarantees: 0 emails sent and 0 database timestamp mutations."""
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=103,
            external_id="match-idemp-3",
            change_type="STATUS_CHANGED",
            field_name="status",
            old_value="LIVE",
            new_value="COMPLETED",
            severity="IMPORTANT",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        backend = TestEmailBackend()
        service = NotificationService(session=db_session, backend=backend, recipients=test_recipients)

        res_dry = service.run(dry_run=True)
        assert res_dry.is_dry_run is True
        assert res_dry.emails_sent == 0
        assert len(backend.sent_messages) == 0

        # Event notified_at must remain None
        db_session.refresh(event)
        assert event.notified_at is None

    def test_console_and_smtp_backends_safe_execution(self, test_recipients):
        """Verifies ConsoleEmailBackend executes and SmtpEmailBackend validates configuration properly."""
        from app.notifications.exceptions import ConfigurationError
        from app.notifications.models import EmailMessage

        msg = EmailMessage(
            from_addr="alerts@fancode.local",
            to_addrs=["admin@fancode.local"],
            subject="Test Console Subject",
            html_body="<p>Test Body</p>",
            text_body="Test Body",
        )

        console_backend = ConsoleEmailBackend()
        result_console = console_backend.send(msg)
        assert result_console is True

        # SmtpEmailBackend without configured host raises ConfigurationError
        smtp_backend = SmtpEmailBackend(host="", port=587)
        with pytest.raises(ConfigurationError, match="SMTP host is not configured"):
            smtp_backend.send(msg)

    def test_batch_grouping_determinism(self, db_session):
        """Verifies that grouping identical sets of events produces deterministic, identical batch keys."""
        from app.change_detection.models import ProposedChangeEvent

        ev1 = ProposedChangeEvent(
            entity_type="MATCH",
            entity_id=200,
            change_type="CREATED",
            new_value="Match X",
            severity="IMPORTANT",
        )
        ev2 = ProposedChangeEvent(
            entity_type="MATCH",
            entity_id=200,
            change_type="STATUS_CHANGED",
            field_name="status",
            new_value="LIVE",
            severity="CRITICAL",
        )

        batch_a = EventGrouper.create_batch([ev1, ev2], scrape_run_id=99)
        batch_b = EventGrouper.create_batch([ev1, ev2], scrape_run_id=99)

        assert batch_a.batch_key == batch_b.batch_key
        assert batch_a.event_count == batch_b.event_count
