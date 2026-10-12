"""
exceptions.py – Exception hierarchy for Alerting / Notification Engine (Phase 9).
"""

from __future__ import annotations


class NotificationError(Exception):
    """Base exception for all notification engine errors."""
    pass


class ConfigurationError(NotificationError):
    """Raised when notification or SMTP configuration is invalid/missing."""
    pass


class DeliveryError(NotificationError):
    """Raised when email delivery fails via SMTP or another transport backend."""
    pass


class RenderingError(NotificationError):
    """Raised when rendering HTML or plain-text email templates fails."""
    pass


class DeduplicationError(NotificationError):
    """Raised when deduplication processing encounters an unrecoverable state."""
    pass
