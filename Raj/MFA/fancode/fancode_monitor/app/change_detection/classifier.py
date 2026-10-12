"""
classifier.py – Centralized change classification policy for FanCode entities.

Defines meaningful vs. noisy fields and assigns semantic change types
(CREATED, UPDATED, STATUS_CHANGED, REMOVED) along with conservative severity levels.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from app.change_detection.models import ChangeType, EntityType, Severity

logger = logging.getLogger(__name__)

# Centralized field classification policy
# Only human-relevant business and fixture changes are tracked as meaningful.
MEANINGFUL_FIELDS: Dict[str, List[str]] = {
    EntityType.MATCH.value: [
        "title",
        "status",
        "start_time",
        "match_date",
        "venue",
        "team_a_name",
        "team_b_name",
    ],
    EntityType.VIDEO.value: [
        "title",
        "video_type",
        "duration_seconds",
        "description",
    ],
    EntityType.TOUR.value: [
        "name",
        "start_date",
        "end_date",
        "status",
        "description",
    ],
    EntityType.SPORT.value: [
        "name",
        "description",
    ],
}

# Technical, volatile, navigation, and live-score counters are explicitly classified as noisy.
NOISY_FIELDS: Dict[str, Set[str]] = {
    EntityType.MATCH.value: {
        "source_url",
        "url",
        "slug",
        "image_url",
        "team_a_logo_url",
        "team_b_logo_url",
        "team_a_id",
        "team_b_id",
        "team_a_external_id",
        "team_b_external_id",
        "sport_id",
        "tour_id",
        "score_summary",
        "score",
        "innings",
        "overs",
        "wickets",
        "points",
        "elapsed_time",
        "period",
        "quarter",
        "stream_available",
        "stream_language",
        "thumbnail_url",
        "description",
        "raw_metadata",
        "metadata",
        "metadata_json",
        "last_seen_at",
        "updated_at",
        "created_at",
        "first_seen_at",
        "scrape_run_id",
    },
    EntityType.VIDEO.value: {
        "source_url",
        "url",
        "slug",
        "thumbnail_url",
        "image_url",
        "match_id",
        "tour_id",
        "sport_id",
        "published_at",
        "raw_metadata",
        "metadata",
        "metadata_json",
        "last_seen_at",
        "updated_at",
        "created_at",
        "first_seen_at",
        "views",
        "scrape_run_id",
    },
    EntityType.TOUR.value: {
        "source_url",
        "url",
        "slug",
        "image_url",
        "sport_id",
        "raw_metadata",
        "metadata",
        "metadata_json",
        "last_seen_at",
        "updated_at",
        "created_at",
        "first_seen_at",
        "scrape_run_id",
    },
    EntityType.SPORT.value: {
        "source_url",
        "url",
        "slug",
        "image_url",
        "is_active",
        "raw_metadata",
        "metadata",
        "metadata_json",
        "last_seen_at",
        "updated_at",
        "created_at",
        "first_seen_at",
        "scrape_run_id",
    },
}


# Regex for identifying non-semantic placeholder titles (e.g. 'Match 1', 'match-2', 'Fixture 3')
# Transitions from placeholders to verified names are initial enrichments, not change alerts.
PLACEHOLDER_TITLE_PATTERN = re.compile(
    r"^(match|fixture)\s*[-_#]?\s*\d*$",
    re.IGNORECASE,
)


class ChangeClassifier:
    """Classifies detected differences into meaningful change events with appropriate severity."""

    @staticmethod
    def is_placeholder_title(val: Optional[str]) -> bool:
        """Returns True if the string matches a generic placeholder title pattern."""
        if not val or not str(val).strip():
            return True
        return bool(PLACEHOLDER_TITLE_PATTERN.match(str(val).strip()))

    @staticmethod
    def get_meaningful_fields(entity_type: str) -> List[str]:
        """Return the list of monitored meaningful fields for an entity type."""
        return MEANINGFUL_FIELDS.get(entity_type.upper(), [])

    @staticmethod
    def is_meaningful_field(entity_type: str, field_name: str) -> bool:
        """Return True if the field is monitored for meaningful change detection."""
        allowed = MEANINGFUL_FIELDS.get(entity_type.upper(), [])
        return field_name in allowed

    @staticmethod
    def is_noisy_field(entity_type: str, field_name: str) -> bool:
        """Return True if the field represents volatile operational noise (e.g. live score)."""
        noisy = NOISY_FIELDS.get(entity_type.upper(), set())
        return field_name in noisy

    @staticmethod
    def classify_status_transition(old_status: Optional[str], new_status: Optional[str]) -> Tuple[str, str]:
        """
        Classifies status transitions and assigns appropriate severity.
        Returns (change_type, severity).
        """
        old_s = (old_status or "").upper()
        new_s = (new_status or "").upper()

        # Match cancelled is critical
        if new_s in ("CANCELLED", "ABANDONED"):
            return ChangeType.STATUS_CHANGED.value, Severity.CRITICAL.value

        # Match postponed is important; match going LIVE is critical
        if new_s in ("POSTPONED", "DELAYED"):
            return ChangeType.STATUS_CHANGED.value, Severity.IMPORTANT.value

        if new_s == "LIVE" and old_s in ("UPCOMING", "SCHEDULED", "UNKNOWN", ""):
            return ChangeType.STATUS_CHANGED.value, Severity.CRITICAL.value

        # Match completed
        if new_s == "COMPLETED":
            return ChangeType.STATUS_CHANGED.value, Severity.INFO.value

        # Status transition to UNKNOWN / unverified is scraper ambiguity and strictly LOW severity
        if new_s in ("UNKNOWN", "", "UNCONFIRMED", "UNVERIFIED", "NONE", "NULL"):
            return ChangeType.STATUS_CHANGED.value, Severity.LOW.value

        return ChangeType.STATUS_CHANGED.value, Severity.INFO.value

    @classmethod
    def classify_field_change(
        cls,
        entity_type: str,
        field_name: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        old_val: Optional[str] = None,
        new_val: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Determine (change_type, severity) for a changed field.
        Returns None if the field is noisy or unmonitored.
        """
        actual_old = old_value if old_value is not None else old_val
        actual_new = new_value if new_value is not None else new_val
        e_type = entity_type.upper()

        # Explicitly reject noisy fields
        if cls.is_noisy_field(e_type, field_name):
            return None

        # Explicitly require field to be in meaningful allowlist
        if not cls.is_meaningful_field(e_type, field_name):
            return None

        # Placeholder title churn is scraper fallback noise in either direction.
        if field_name in ("title", "name"):
            if cls.is_placeholder_title(actual_old) or cls.is_placeholder_title(actual_new):
                return None

        # Status field change
        if field_name == "status":
            return cls.classify_status_transition(actual_old, actual_new)

        # High-impact match field updates
        if e_type == EntityType.MATCH.value and field_name in (
            "venue", "match_date", "start_time", "team_a_name", "team_b_name", "title"
        ):
            return ChangeType.UPDATED.value, Severity.IMPORTANT.value

        # Other meaningful fields in allowlist
        return ChangeType.UPDATED.value, Severity.INFO.value

    @staticmethod
    def classify_severity(entity_type: str, change_type: str) -> str:
        """Classifies severity for entity-level changes (e.g. CREATED, REMOVED)."""
        e_type = entity_type.upper()
        c_type = change_type.upper()
        if c_type == ChangeType.CREATED.value:
            if e_type == EntityType.MATCH.value:
                return Severity.IMPORTANT.value
            return Severity.INFO.value
        elif c_type == ChangeType.REMOVED.value:
            return Severity.IMPORTANT.value
        return Severity.INFO.value

    @staticmethod
    def classify_new_entity(entity_type: str) -> Tuple[str, str]:
        """Returns (change_type, severity) for newly observed entity."""
        e_type = entity_type.upper()
        if e_type == EntityType.MATCH.value:
            return ChangeType.CREATED.value, Severity.IMPORTANT.value
        elif e_type == EntityType.VIDEO.value:
            return ChangeType.CREATED.value, Severity.INFO.value
        elif e_type == EntityType.TOUR.value:
            return ChangeType.CREATED.value, Severity.INFO.value
        else:
            return ChangeType.CREATED.value, Severity.INFO.value

    @staticmethod
    def classify_removed_entity(entity_type: str) -> Tuple[str, str]:
        """Returns (change_type, severity) for a reliably removed entity."""
        e_type = entity_type.upper()
        if e_type == EntityType.MATCH.value:
            return ChangeType.REMOVED.value, Severity.IMPORTANT.value
        return ChangeType.REMOVED.value, Severity.INFO.value
