"""
repository.py – Database repository for notification batches, deliveries, and audit links (Phase 9).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.connection import utc_now
from app.database.models import (
    ChangeEvent,
    NotificationBatch,
    NotificationDelivery,
    NotificationEventLink,
)

logger = logging.getLogger(__name__)


class NotificationRepository:
    """
    Data access layer for notification auditing and change event status updates.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_unnotified_events(
        self,
        limit: int = 100,
        entity_type: Optional[str] = None,
        severity: Optional[str] = None,
        change_type: Optional[str] = None,
        scrape_run_id: Optional[int] = None,
    ) -> List[ChangeEvent]:
        """
        Retrieves unnotified ChangeEvents ordered by detection timestamp.
        """
        stmt = select(ChangeEvent).where(ChangeEvent.notified_at.is_(None))

        if entity_type:
            stmt = stmt.where(ChangeEvent.entity_type == entity_type.upper())
        if severity:
            stmt = stmt.where(ChangeEvent.severity == severity.upper())
        if change_type:
            stmt = stmt.where(ChangeEvent.change_type == change_type.upper())
        if scrape_run_id is not None:
            stmt = stmt.where(ChangeEvent.scrape_run_id == scrape_run_id)

        stmt = stmt.order_by(ChangeEvent.detected_at).limit(limit)
        return list(self.session.scalars(stmt).all())

    def get_batch_by_key(self, batch_key: str) -> Optional[NotificationBatch]:
        """Retrieves an existing batch by its deterministic SHA256 key."""
        stmt = select(NotificationBatch).where(NotificationBatch.batch_key == batch_key)
        return self.session.scalars(stmt).first()

    def get_recent_batches(self, limit: int = 20) -> List[NotificationBatch]:
        """Retrieves recent notification batches."""
        stmt = select(NotificationBatch).order_by(desc(NotificationBatch.created_at)).limit(limit)
        return list(self.session.scalars(stmt).all())

    def create_batch(
        self,
        batch_key: str,
        subject: str,
        event_count: int = 0,
        recipient_count: int = 0,
        status: str = "PENDING",
        error_message: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> NotificationBatch:
        """
        Creates or updates a NotificationBatch audit record.
        """
        now = utc_now()
        existing = self.get_batch_by_key(batch_key)
        if existing:
            existing.subject = subject
            existing.event_count = event_count
            existing.recipient_count = recipient_count
            existing.status = status
            existing.error_message = error_message
            existing.updated_at = now
            if metadata_json:
                existing.metadata_json = metadata_json
            self.session.flush()
            return existing

        batch = NotificationBatch(
            batch_key=batch_key,
            subject=subject,
            status=status,
            event_count=event_count,
            recipient_count=recipient_count,
            error_message=error_message,
            metadata_json=metadata_json,
            created_at=now,
            updated_at=now,
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def link_events_to_batch(self, batch_id: int, event_ids: List[int]) -> None:
        """Creates association rows between a NotificationBatch and ChangeEvents."""
        for eid in event_ids:
            # Check if link already exists
            stmt = select(NotificationEventLink).where(
                NotificationEventLink.batch_id == batch_id,
                NotificationEventLink.change_event_id == eid,
            )
            exists = self.session.scalars(stmt).first()
            if not exists:
                link = NotificationEventLink(batch_id=batch_id, change_event_id=eid)
                self.session.add(link)
        self.session.flush()

    def record_delivery(
        self,
        batch_id: int,
        recipient: str,
        status: str = "PENDING",
        provider: str = "console",
        error_message: Optional[str] = None,
    ) -> NotificationDelivery:
        """Records a recipient delivery attempt."""
        now = utc_now()
        delivery = NotificationDelivery(
            batch_id=batch_id,
            recipient=recipient,
            status=status,
            provider=provider,
            attempted_at=now,
            sent_at=now if status == "SENT" else None,
            error_message=error_message,
        )
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def mark_batch_sent(self, batch_id: int) -> Optional[NotificationBatch]:
        """Marks a batch as successfully SENT."""
        batch = self.session.get(NotificationBatch, batch_id)
        if batch:
            batch.status = "SENT"
            batch.sent_at = utc_now()
            batch.error_message = None
            self.session.flush()
        return batch

    def mark_batch_failed(self, batch_id: int, error_message: str) -> Optional[NotificationBatch]:
        """Marks a batch as FAILED."""
        batch = self.session.get(NotificationBatch, batch_id)
        if batch:
            batch.status = "FAILED"
            batch.error_message = error_message
            self.session.flush()
        return batch

    def mark_events_notified(self, event_ids: List[int]) -> int:
        """
        Marks the specified ChangeEvents as successfully notified (sets notified_at).
        """
        if not event_ids:
            return 0

        now = utc_now()
        stmt = select(ChangeEvent).where(ChangeEvent.id.in_(event_ids))
        events = list(self.session.scalars(stmt).all())
        for e in events:
            e.notified_at = now
        self.session.flush()
        return len(events)
