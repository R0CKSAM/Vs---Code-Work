"""
deduplicator.py – Notification deduplication logic for FanCode events (Phase 9).

Prevents resending already-notified ChangeEvents and checks batch idempotency.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Set

from sqlalchemy.orm import Session

from app.database.models import ChangeEvent, NotificationBatch

logger = logging.getLogger(__name__)


class NotificationDeduplicator:
    """
    Checks database records to prevent duplicate notification delivery.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def filter_unnotified_events(self, events: List[Any]) -> List[Any]:
        """
        Filters out events that have already been marked as notified (notified_at is not None).
        """
        unnotified: List[Any] = []
        for e in events:
            # If in-memory object has notified_at set, skip
            if getattr(e, "notified_at", None) is not None:
                continue

            # If event has an ID, verify against database state if attached
            e_id = getattr(e, "id", None)
            if e_id is not None:
                db_event = self.session.get(ChangeEvent, e_id)
                if db_event and db_event.notified_at is not None:
                    continue

            unnotified.append(e)

        return unnotified

    def is_batch_already_sent(self, batch_key: str) -> bool:
        """
        Returns True if a batch with the given batch_key has already been successfully SENT.
        Failed batches return False to allow retries.
        """
        from sqlalchemy import select

        stmt = select(NotificationBatch).where(
            NotificationBatch.batch_key == batch_key,
            NotificationBatch.status == "SENT",
        )
        existing = self.session.scalars(stmt).first()
        return existing is not None
