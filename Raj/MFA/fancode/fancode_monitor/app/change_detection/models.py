"""
models.py – Data models for the FanCode Change Detection Engine (Phase 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(str, Enum):
    MATCH = "MATCH"
    SPORT = "SPORT"
    TOUR = "TOUR"
    VIDEO = "VIDEO"


class ChangeType(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    REMOVED = "REMOVED"


class Severity(str, Enum):
    INFO = "INFO"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


@dataclass
class ProposedChangeEvent:
    """A classified, meaningful change candidate ready for deduplication and persistence."""
    entity_type: str
    entity_id: int
    change_type: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    severity: str = Severity.INFO.value
    external_id: Optional[str] = None
    source_url: Optional[str] = None
    scrape_run_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_key(self) -> str:
        """Deterministic fingerprint for event deduplication."""
        return (
            f"{self.entity_type}:{self.entity_id}:{self.change_type}:"
            f"{self.field_name or ''}:{self.new_value or ''}"
        )


@dataclass
class ChangeDetectionResult:
    """Summary of a change detection run across entities."""
    entities_checked: int = 0
    created_events: int = 0
    updated_events: int = 0
    status_events: int = 0
    removed_events: int = 0
    ignored_changes: int = 0
    errors: int = 0
    events: List[ProposedChangeEvent] = field(default_factory=list)
