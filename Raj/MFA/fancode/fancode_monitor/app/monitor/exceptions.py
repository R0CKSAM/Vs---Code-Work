"""
exceptions.py – Exception hierarchy and Error Classification for Monitor & Orchestration Engine (Phase 10 & 11).
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple


class ErrorCategory(str, Enum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    LOCK_ERROR = "LOCK_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    SCRAPER_ERROR = "SCRAPER_ERROR"
    PARSER_ERROR = "PARSER_ERROR"
    NOTIFICATION_ERROR = "NOTIFICATION_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    INTERRUPTION = "INTERRUPTION"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class ErrorAction(str, Enum):
    RETRY = "RETRY"
    CONTINUE = "CONTINUE"
    DEGRADE = "DEGRADE"
    ABORT = "ABORT"


class MonitorError(Exception):
    """Base exception for all monitor and pipeline orchestration errors."""
    category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR
    action: ErrorAction = ErrorAction.ABORT


class LockError(MonitorError):
    """Base exception for pipeline locking failures."""
    category = ErrorCategory.LOCK_ERROR
    action = ErrorAction.ABORT


class LockAcquisitionError(LockError):
    """Raised when another active monitor process holds the exclusive lock."""
    pass


class FatalPipelineError(MonitorError):
    """Raised when an unrecoverable failure terminates pipeline execution."""
    action = ErrorAction.ABORT


class StageExecutionError(MonitorError):
    """Raised when a pipeline stage encounters an error."""
    category = ErrorCategory.SCRAPER_ERROR
    action = ErrorAction.CONTINUE


class StageTimeoutError(StageExecutionError):
    """Raised when a pipeline stage exceeds its configured timeout."""
    category = ErrorCategory.TIMEOUT_ERROR
    action = ErrorAction.RETRY


def classify_error(exc: BaseException) -> Tuple[ErrorCategory, ErrorAction]:
    """
    Classifies any python exception into an ErrorCategory and recommended ErrorAction.
    """
    if isinstance(exc, KeyboardInterrupt):
        return ErrorCategory.INTERRUPTION, ErrorAction.ABORT

    if isinstance(exc, LockAcquisitionError):
        return ErrorCategory.LOCK_ERROR, ErrorAction.ABORT

    if isinstance(exc, LockError):
        return ErrorCategory.LOCK_ERROR, ErrorAction.ABORT

    # Check for database errors
    name = type(exc).__name__
    module = type(exc).__module__
    if "sqlalchemy" in module or "sqlite" in module or "Database" in name or "OperationalError" in name:
        return ErrorCategory.DATABASE_ERROR, ErrorAction.ABORT

    # Timeout errors
    if isinstance(exc, (StageTimeoutError, TimeoutError)) or "Timeout" in name:
        return ErrorCategory.TIMEOUT_ERROR, ErrorAction.RETRY

    # Check for network/connection errors
    if isinstance(exc, (ConnectionError, ConnectionResetError)):
        return ErrorCategory.NETWORK_ERROR, ErrorAction.RETRY

    # Notification
    if "Notification" in name or "Email" in name:
        return ErrorCategory.NOTIFICATION_ERROR, ErrorAction.CONTINUE

    # Configuration
    if "Configuration" in name or "Config" in name or "Settings" in name:
        return ErrorCategory.CONFIGURATION_ERROR, ErrorAction.ABORT

    # MonitorError subclass defaults
    if isinstance(exc, MonitorError):
        return exc.category, exc.action

    return ErrorCategory.UNKNOWN_ERROR, ErrorAction.CONTINUE
