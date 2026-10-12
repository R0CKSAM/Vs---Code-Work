"""
policy.py – Centralized notification policy for FanCode change events (Phase 9).

Evaluates whether a ChangeEvent produced by Phase 8 is notifiable based on:
- Entity type (MATCH, VIDEO, TOUR, SPORT)
- Change type (CREATED, UPDATED, STATUS_CHANGED, REMOVED)
- Severity level (CRITICAL, IMPORTANT, INFO, LOW)
- Meaningful vs. noisy field classifications
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.change_detection.models import ChangeType, EntityType, Severity
from app.change_detection.classifier import NOISY_FIELDS, ChangeClassifier

logger = logging.getLogger(__name__)


class NotificationPolicy:
    """
    Centralized evaluation policy for alerting on ChangeEvent records.
    Consumes Phase 8 change events without mutating them.
    """

    @classmethod
    def is_notifiable(cls, event: Any) -> bool:
        """
        Determines whether a single ChangeEvent is eligible for notification delivery.
        """
        if event is None:
            return False

        entity_type = (getattr(event, "entity_type", "") or "").upper()
        change_type = (getattr(event, "change_type", "") or "").upper()
        severity = (getattr(event, "severity", "") or Severity.INFO.value).upper()
        field_name = getattr(event, "field_name", None)

        # 1. Reject LOW severity by default
        if severity == "LOW":
            return False

        # 2. Reject noisy fields explicitly
        if field_name:
            entity_noisy = NOISY_FIELDS.get(entity_type, set())
            if field_name in entity_noisy:
                return False

        # 3. Suppress placeholder-to-verified title transitions (initial enrichment)
        if field_name in ("title", "name"):
            old_val = getattr(event, "old_value", None)
            if ChangeClassifier.is_placeholder_title(old_val):
                return False

        # 4. CRITICAL severity events are ALWAYS notifiable
        if severity == Severity.CRITICAL.value:
            return True

        # 5. Entity & Change-type specific evaluation
        if change_type == ChangeType.STATUS_CHANGED.value:
            # Status changes for matches are always notifiable (LIVE, COMPLETED, CANCELLED, POSTPONED, etc.)
            return True

        if change_type == ChangeType.CREATED.value:
            # New matches, videos, tours, and sports are notifiable
            return entity_type in (
                EntityType.MATCH.value,
                EntityType.VIDEO.value,
                EntityType.TOUR.value,
                EntityType.SPORT.value,
            )

        if change_type == ChangeType.REMOVED.value:
            # Reliable removals from complete snapshot are notifiable if IMPORTANT/CRITICAL
            return severity in (Severity.IMPORTANT.value, Severity.CRITICAL.value)

        if change_type == ChangeType.UPDATED.value:
            # Updates with IMPORTANT/CRITICAL severity (e.g. venue, date, team, title) are notifiable
            if severity in (Severity.IMPORTANT.value, Severity.CRITICAL.value):
                return True
            # Meaningful video/tour/sport updates
            if entity_type in (EntityType.VIDEO.value, EntityType.TOUR.value, EntityType.SPORT.value) and field_name in (
                "title", "name", "start_date", "end_date", "status", "video_type", "duration_seconds", "description"
            ):
                return True
            # General updates for MATCH title/venue/teams
            if entity_type == EntityType.MATCH.value and field_name in (
                "title", "venue", "team_a_name", "team_b_name", "start_time", "match_date"
            ):
                return True
            return False

        # Disallow any other unhandled changes
        return False

    @classmethod
    def filter_events(cls, events: List[Any]) -> List[Any]:
        """Filter a list of ChangeEvent objects, retaining only notifiable ones."""
        return [e for e in events if cls.is_notifiable(e)]
