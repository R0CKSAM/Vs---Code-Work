"""
logging_config.py – Structured Logging and Secret Redaction for FanCode Monitor (Phase 11).

Provides:
- Secret redaction for credentials, passwords, auth headers, and cookies.
- Context injection (run_id, stage, scrape_run_id) into log records.
- Standardized text and JSON structured formatters.
- Centralized logger configuration.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.observability.context import get_correlation_context

# Sensitive key patterns to redact
SENSITIVE_PATTERNS = [
    re.compile(r"(password['\"]?\s*[:=]\s*['\"]?)([^'\"\s&,]+)", re.IGNORECASE),
    re.compile(r"(smtp_password['\"]?\s*[:=]\s*['\"]?)([^'\"\s&,]+)", re.IGNORECASE),
    re.compile(r"(secret['\"]?\s*[:=]\s*['\"]?)([^'\"\s&,]+)", re.IGNORECASE),
    re.compile(r"(token['\"]?\s*[:=]\s*['\"]?)([^'\"\s&,]+)", re.IGNORECASE),
    re.compile(r"(authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+)([^'\"\s&,]+)", re.IGNORECASE),
    re.compile(r"(cookie['\"]?\s*[:=]\s*['\"]?)([^'\"\r\n]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)([^'\"\s&,]+)", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Replaces detected sensitive secrets in strings with [REDACTED]."""
    if not isinstance(text, str):
        return text
    result = text
    for pat in SENSITIVE_PATTERNS:
        result = pat.sub(r"\1[REDACTED]", result)
    return result


class SecretRedactionFilter(logging.Filter):
    """Logging filter that automatically redacts secrets and injects correlation metadata."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_secrets(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(redact_secrets(v) if isinstance(v, str) else v for v in record.args)

        # Inject correlation context if not explicitly set
        ctx = get_correlation_context()
        if not hasattr(record, "run_id") or record.run_id is None:
            record.run_id = ctx.get("run_id")
        if not hasattr(record, "stage") or record.stage is None:
            record.stage = ctx.get("stage")
        if not hasattr(record, "scrape_run_id") or record.scrape_run_id is None:
            record.scrape_run_id = ctx.get("scrape_run_id")

        return True


class StructuredFormatter(logging.Formatter):
    """
    Structured log formatter.
    Outputs correlated logs with:
    timestamp level logger [run_id stage scrape_run_id] message
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        level = record.levelname
        name = record.name

        context_parts = []
        run_id = getattr(record, "run_id", None)
        if run_id:
            context_parts.append(f"run_id={run_id}")
        stage = getattr(record, "stage", None)
        if stage:
            context_parts.append(f"stage={stage}")
        scrape_run_id = getattr(record, "scrape_run_id", None)
        if scrape_run_id:
            context_parts.append(f"scrape_run_id={scrape_run_id}")

        ctx_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        msg = record.getMessage()

        base_line = f"{timestamp} {level:<5} {name}{ctx_str}: {msg}"

        if record.exc_info:
            base_line += "\n" + redact_secrets(self.formatException(record.exc_info))

        return base_line


class JsonStructuredFormatter(logging.Formatter):
    """JSON log formatter for machine readability."""

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            "run_id": getattr(record, "run_id", None),
            "stage": getattr(record, "stage", None),
            "scrape_run_id": getattr(record, "scrape_run_id", None),
        }
        if record.exc_info:
            data["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(data)


def configure_logging(
    level: str = "INFO",
    structured_json: bool = False,
    logger_name: Optional[str] = None,
) -> None:
    """Configures structured logging and attaches redaction filter."""
    target_logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    target_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers if already configured
    if not any(isinstance(f, SecretRedactionFilter) for h in target_logger.handlers for f in h.filters):
        handler = logging.StreamHandler()
        formatter = JsonStructuredFormatter() if structured_json else StructuredFormatter()
        handler.setFormatter(formatter)
        handler.addFilter(SecretRedactionFilter())
        target_logger.addHandler(handler)
