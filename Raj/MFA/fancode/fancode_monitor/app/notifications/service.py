"""
service.py – Main Notification Engine Service orchestrating the Phase 9 pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.notifications.deduplicator import NotificationDeduplicator
from app.notifications.email_backend import (
    ConsoleEmailBackend,
    EmailBackend,
    TestEmailBackend,
)
from app.notifications.exceptions import DeliveryError, NotificationError
from app.notifications.grouping import EventGrouper
from app.notifications.models import (
    EmailMessage,
    EmailRecipientConfig,
    NotificationBatchDraft,
    NotificationRunResult,
    NotificationStatus,
)
from app.notifications.policy import NotificationPolicy
from app.notifications.renderer import NotificationRenderer
from app.notifications.repository import NotificationRepository
from app.notifications.smtp_backend import SmtpEmailBackend

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Orchestrates candidate collection, policy filtering, deduplication,
    batching, rendering, email dispatch, and audit persistence.
    """

    def __init__(
        self,
        session: Session,
        backend: Optional[EmailBackend] = None,
        recipients: Optional[EmailRecipientConfig] = None,
    ) -> None:
        self.session = session
        self.repo = NotificationRepository(session)
        self.deduplicator = NotificationDeduplicator(session)
        self.backend = backend or self._resolve_backend()
        self.recipients = recipients or self._resolve_recipients()

    # -------------------------------------------------------------------------
    # Public Pipeline API
    # -------------------------------------------------------------------------

    def run(
        self,
        limit: int = 100,
        entity_type: Optional[str] = None,
        severity: Optional[str] = None,
        change_type: Optional[str] = None,
        scrape_run_id: Optional[int] = None,
        dry_run: bool = False,
    ) -> NotificationRunResult:
        """
        Fetches unnotified ChangeEvents from the database and processes notifications.
        """
        events = self.repo.get_unnotified_events(
            limit=limit,
            entity_type=entity_type,
            severity=severity,
            change_type=change_type,
            scrape_run_id=scrape_run_id,
        )
        return self.process_events(events, scrape_run_id=scrape_run_id, dry_run=dry_run)

    def process_events(
        self,
        events: List[Any],
        scrape_run_id: Optional[int] = None,
        dry_run: bool = False,
    ) -> NotificationRunResult:
        """
        Executes the notification pipeline over a provided list of ChangeEvents.
        """
        result = NotificationRunResult(
            events_inspected=len(events),
            is_dry_run=dry_run,
        )

        if not events:
            logger.info("No change events provided for notification processing.")
            return result

        # 1. Filter via Policy
        eligible_events = NotificationPolicy.filter_events(events)
        result.events_eligible = len(eligible_events)
        result.events_filtered_out = len(events) - len(eligible_events)

        # Mark ineligible events so they don't repeatedly queue
        if not dry_run and result.events_filtered_out > 0:
            from datetime import datetime, timezone
            for ev in events:
                if ev not in eligible_events and getattr(ev, "id", None) and hasattr(ev, "notified_at"):
                    ev.notified_at = datetime.now(timezone.utc)
            self.session.commit()

        if not eligible_events:
            logger.info("All change events were filtered out by notification policy.")
            return result

        # 2. Deduplicate
        unnotified_events = self.deduplicator.filter_unnotified_events(eligible_events)
        result.events_deduplicated = len(eligible_events) - len(unnotified_events)

        if not unnotified_events:
            logger.info("All eligible events were already notified (deduplicated).")
            return result

        # 3. Group into bounded batches
        max_batch_size = getattr(settings, "NOTIFICATION_MAX_EVENTS_PER_BATCH", 100)
        batches = EventGrouper.create_batches(
            events=unnotified_events,
            scrape_run_id=scrape_run_id,
            max_events=max_batch_size,
        )

        for batch in batches:
            if not batch or not batch.events:
                continue

            # 4. Check if exact batch key was already successfully sent
            if self.deduplicator.is_batch_already_sent(batch.batch_key):
                logger.info("Batch %s was already successfully sent. Skipping.", batch.batch_key[:12])
                result.events_deduplicated += len(batch.events)
                continue

            # 5. Render Email
            email_msg = NotificationRenderer.build_email_message(batch, self.recipients)
            batch.email_message = email_msg
            batch.subject = email_msg.subject
            result.batches.append(batch)
            result.batches_created += 1

            # 6. Deliver & Audit
            if dry_run:
                batch.status = NotificationStatus.DRY_RUN
                logger.info("DRY-RUN: Digest generated with %d events. (Subject: %s)", len(batch.events), batch.subject)
                continue

            self._dispatch_and_audit(batch, result)
        return result

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _dispatch_and_audit(self, batch: NotificationBatchDraft, result: NotificationRunResult) -> None:
        """
        Persists batch state, sends via backend, and transactionally updates audit records.
        """
        assert batch.email_message is not None

        # 1. Create or update batch in DB with PENDING status
        db_batch = self.repo.create_batch(
            batch_key=batch.batch_key,
            subject=batch.subject,
            event_count=batch.event_count,
            recipient_count=len(self.recipients.all_recipients),
            status="PENDING",
            metadata_json={"scrape_run_id": batch.scrape_run_id},
        )

        # 2. Link change event IDs
        event_ids = [getattr(e, "id", None) for e in batch.events if getattr(e, "id", None) is not None]
        if event_ids:
            self.repo.link_events_to_batch(db_batch.id, event_ids)

        # 3. Attempt delivery
        delivery_failed = False
        last_error = ""

        try:
            self.backend.send(batch.email_message)
            batch.status = NotificationStatus.SENT
            result.emails_sent += 1

            # Record successful delivery audit for each recipient
            provider_name = type(self.backend).__name__.replace("EmailBackend", "").lower() or "console"
            for rcpt in self.recipients.all_recipients:
                self.repo.record_delivery(
                    batch_id=db_batch.id,
                    recipient=rcpt,
                    status="SENT",
                    provider=provider_name,
                )

            # Mark batch SENT and mark ChangeEvents as notified
            self.repo.mark_batch_sent(db_batch.id)
            if event_ids:
                self.repo.mark_events_notified(event_ids)
            self.session.commit()

        except Exception as e:
            delivery_failed = True
            last_error = str(e)
            batch.status = NotificationStatus.FAILED
            batch.error_message = last_error
            result.deliveries_failed += 1
            result.errors.append(last_error)

            # Record failed delivery audit
            provider_name = type(self.backend).__name__.replace("EmailBackend", "").lower() or "console"
            for rcpt in self.recipients.all_recipients:
                self.repo.record_delivery(
                    batch_id=db_batch.id,
                    recipient=rcpt,
                    status="FAILED",
                    provider=provider_name,
                    error_message=last_error,
                )

            self.repo.mark_batch_failed(db_batch.id, error_message=last_error)
            self.session.commit()
            logger.error("Notification delivery failed for batch %s: %s", batch.batch_key[:12], e)

    def _resolve_backend(self) -> EmailBackend:
        """Instantiates configured EmailBackend."""
        backend_type = (getattr(settings, "EMAIL_BACKEND", "console") or "console").lower()
        output_dir = getattr(settings, "NOTIFICATION_OUTPUT_DIR", None)

        if backend_type == "smtp" or getattr(settings, "SMTP_ENABLED", False):
            return SmtpEmailBackend(
                host=getattr(settings, "SMTP_HOST", ""),
                port=getattr(settings, "SMTP_PORT", 587),
                username=getattr(settings, "SMTP_USER", ""),
                password=getattr(settings, "SMTP_PASSWORD", ""),
                use_tls=getattr(settings, "SMTP_USE_TLS", True),
                use_ssl=getattr(settings, "SMTP_USE_SSL", False) if getattr(settings, "SMTP_PORT", 587) != 465 else True,
                timeout=getattr(settings, "SMTP_TIMEOUT_SECONDS", 15),
            )
        elif backend_type == "test":
            return TestEmailBackend()
        else:
            return ConsoleEmailBackend(output_dir=output_dir)

    def _resolve_recipients(self) -> EmailRecipientConfig:
        """Parses configured sender and recipient email addresses."""
        configured_from = getattr(settings, "ALERT_EMAIL_FROM", "")
        smtp_user = getattr(settings, "SMTP_USER", "")

        if configured_from and configured_from != "alerts@fancode-monitor.local":
            from_addr = configured_from
        elif smtp_user and "@" in smtp_user:
            from_addr = smtp_user
        else:
            from_addr = configured_from or "alerts@fancode-monitor.local"

        to_raw = getattr(settings, "ALERT_EMAIL_TO", "") or getattr(settings, "ALERT_RECIPIENTS", "") or "admin@fancode-monitor.local"
        to_addrs = [addr.strip() for addr in to_raw.split(",") if addr.strip()]

        cc_raw = getattr(settings, "ALERT_EMAIL_CC", "")
        cc_addrs = [addr.strip() for addr in cc_raw.split(",") if addr.strip()]

        bcc_raw = getattr(settings, "ALERT_EMAIL_BCC", "")
        bcc_addrs = [addr.strip() for addr in bcc_raw.split(",") if addr.strip()]

        return EmailRecipientConfig(
            from_addr=from_addr,
            to_addrs=to_addrs or ["admin@fancode-monitor.local"],
            cc_addrs=cc_addrs,
            bcc_addrs=bcc_addrs,
        )
