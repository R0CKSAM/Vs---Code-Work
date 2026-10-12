"""
app.observability – Production Hardening, Logging, Metrics & Diagnostics (Phase 11).
"""

from app.observability.context import (
    clear_correlation_context,
    correlation_scope,
    get_correlation_context,
    set_correlation_context,
)
from app.observability.diagnostics import (
    check_database_integrity,
    collect_system_diagnostics,
    format_diagnostics_text,
)
from app.observability.heartbeat import HeartbeatManager, heartbeat
from app.observability.logging_config import (
    JsonStructuredFormatter,
    SecretRedactionFilter,
    StructuredFormatter,
    configure_logging,
    redact_secrets,
)
from app.observability.metrics import MetricsRegistry, metrics

__all__ = [
    "clear_correlation_context",
    "correlation_scope",
    "get_correlation_context",
    "set_correlation_context",
    "check_database_integrity",
    "collect_system_diagnostics",
    "format_diagnostics_text",
    "HeartbeatManager",
    "heartbeat",
    "JsonStructuredFormatter",
    "SecretRedactionFilter",
    "StructuredFormatter",
    "configure_logging",
    "redact_secrets",
    "MetricsRegistry",
    "metrics",
]
