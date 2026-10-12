"""
models.py – Data models and transfer objects for Alerting / Notification Engine (Phase 9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class EmailRecipientConfig:
    """Configured sender and recipients for alert delivery."""
    from_addr: str
    to_addrs: List[str]
    cc_addrs: List[str] = field(default_factory=list)
    bcc_addrs: List[str] = field(default_factory=list)

    @property
    def all_recipients(self) -> List[str]:
        return list(dict.fromkeys(self.to_addrs + self.cc_addrs + self.bcc_addrs))


@dataclass
class EmailMessage:
    """Rendered multipart email ready for transport."""
    subject: str
    html_body: str
    text_body: str
    from_addr: str
    to_addrs: List[str]
    cc_addrs: List[str] = field(default_factory=list)
    bcc_addrs: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GroupedEntity:
    """Events aggregated for a specific entity in a batch."""
    entity_type: str
    entity_id: int
    external_id: Optional[str] = None
    title: Optional[str] = None
    source_url: Optional[str] = None
    events: List[Any] = field(default_factory=list)  # List[ChangeEvent]
    sport_name: Optional[str] = None
    tour_name: Optional[str] = None
    category: Optional[str] = None


@dataclass
class NotificationBatchDraft:
    """Deterministic in-memory digest batch ready for rendering and delivery."""
    batch_key: str
    events: List[Any] = field(default_factory=list)  # List[ChangeEvent]
    grouped_entities: List[GroupedEntity] = field(default_factory=list)
    subject: str = ""
    email_message: Optional[EmailMessage] = None
    scrape_run_id: Optional[int] = None
    status: NotificationStatus = NotificationStatus.PENDING
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_count(self) -> int:
        return len(self.events)


@dataclass
class NotificationRunResult:
    """Summary of a NotificationService execution run."""
    events_inspected: int = 0
    events_eligible: int = 0
    events_filtered_out: int = 0
    events_deduplicated: int = 0
    batches_created: int = 0
    emails_sent: int = 0
    deliveries_failed: int = 0
    is_dry_run: bool = False
    batches: List[NotificationBatchDraft] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
