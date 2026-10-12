"""
test_observability_logging.py – Unit tests for structured logging and secret redaction (Phase 11).
"""

from __future__ import annotations

import json
import logging
from app.observability.context import correlation_scope
from app.observability.logging_config import (
    JsonStructuredFormatter,
    SecretRedactionFilter,
    StructuredFormatter,
    redact_secrets,
)


class TestSecretRedaction:
    def test_redact_password(self):
        msg = "Connecting with password='mysecretpassword123' to host"
        redacted = redact_secrets(msg)
        assert "mysecretpassword123" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_smtp_password(self):
        msg = "SMTP authentication smtp_password=SuperSecretSMTP"
        redacted = redact_secrets(msg)
        assert "SuperSecretSMTP" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_bearer_token(self):
        msg = "Headers: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        redacted = redact_secrets(msg)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_cookie(self):
        msg = "Session header: Cookie: session_id=abc123secret; user=alice"
        redacted = redact_secrets(msg)
        assert "abc123secret" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_api_key(self):
        msg = "Client api_key=ak_live_999888777"
        redacted = redact_secrets(msg)
        assert "ak_live_999888777" not in redacted
        assert "[REDACTED]" in redacted


class TestStructuredFormatters:
    def test_structured_text_formatter_with_context(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=50,
            msg="Stage completed successfully",
            args=(),
            exc_info=None,
        )
        record.run_id = "run-test-01"
        record.stage = "schedule"
        record.scrape_run_id = 42

        formatted = formatter.format(record)
        assert "INFO" in formatted
        assert "run_id=run-test-01" in formatted
        assert "stage=schedule" in formatted
        assert "scrape_run_id=42" in formatted
        assert "Stage completed successfully" in formatted

    def test_json_structured_formatter(self):
        formatter = JsonStructuredFormatter()
        record = logging.LogRecord(
            name="json_logger",
            level=logging.WARNING,
            pathname=__file__,
            lineno=70,
            msg="Warning message with token=SecretToken99",
            args=(),
            exc_info=None,
        )
        record.run_id = "run-json-123"
        record.stage = "live_now"

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["level"] == "WARNING"
        assert parsed["logger"] == "json_logger"
        assert parsed["run_id"] == "run-json-123"
        assert parsed["stage"] == "live_now"
        assert "SecretToken99" not in parsed["message"]
        assert "[REDACTED]" in parsed["message"]

    def test_secret_redaction_filter_context_injection(self):
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            name="filtered_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=90,
            msg="Attempting connection with password=hiddenPass",
            args=(),
            exc_info=None,
        )

        with correlation_scope(run_id="corr-99", stage="match_detail", scrape_run_id=101):
            res = filt.filter(record)
            assert res is True
            assert record.run_id == "corr-99"
            assert record.stage == "match_detail"
            assert record.scrape_run_id == 101
            assert "hiddenPass" not in record.msg
            assert "[REDACTED]" in record.msg
