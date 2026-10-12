"""
app.notifications – FanCode Alerting & Notification Engine (Phase 9).
"""

from app.notifications.deduplicator import NotificationDeduplicator
from app.notifications.email_backend import (
    ConsoleEmailBackend,
    EmailBackend,
    TestEmailBackend,
)
from app.notifications.exceptions import (
    ConfigurationError,
    DeduplicationError,
    DeliveryError,
    NotificationError,
    RenderingError,
)
from app.notifications.grouping import EventGrouper
from app.notifications.models import (
    DeliveryStatus,
    EmailMessage,
    EmailRecipientConfig,
    GroupedEntity,
    NotificationBatchDraft,
    NotificationRunResult,
    NotificationStatus,
)
from app.notifications.policy import NotificationPolicy
from app.notifications.renderer import NotificationRenderer
from app.notifications.repository import NotificationRepository
from app.notifications.service import NotificationService
from app.notifications.smtp_backend import SmtpEmailBackend

__all__ = [
    "NotificationService",
    "NotificationPolicy",
    "EventGrouper",
    "NotificationDeduplicator",
    "NotificationRenderer",
    "NotificationRepository",
    "EmailBackend",
    "ConsoleEmailBackend",
    "TestEmailBackend",
    "SmtpEmailBackend",
    "NotificationStatus",
    "DeliveryStatus",
    "EmailMessage",
    "EmailRecipientConfig",
    "GroupedEntity",
    "NotificationBatchDraft",
    "NotificationRunResult",
    "NotificationError",
    "ConfigurationError",
    "DeliveryError",
    "RenderingError",
    "DeduplicationError",
]
