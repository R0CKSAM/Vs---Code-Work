"""
test_config_validation.py – Unit tests for configuration validation and boundary checks (Phase 11).
"""

from __future__ import annotations

import pytest
from app.config.settings import Settings
from app.config.validation import (
    ConfigurationValidationError,
    assert_valid_settings,
    validate_settings,
)


class TestConfigValidation:
    def test_default_settings_pass_validation(self):
        cfg = Settings()
        errors = validate_settings(cfg)
        assert len(errors) == 0
        assert_valid_settings(cfg)

    def test_invalid_url_detected(self):
        cfg = Settings(BASE_URL="not-a-valid-url")
        errors = validate_settings(cfg)
        assert any("BASE_URL must be a valid HTTP/HTTPS URL" in e for e in errors)

    def test_negative_timeout_detected(self):
        cfg = Settings(MONITOR_RUN_TIMEOUT_SECONDS=-10)
        errors = validate_settings(cfg)
        assert any("MONITOR_RUN_TIMEOUT_SECONDS must be positive" in e for e in errors)

    def test_negative_interval_detected(self):
        cfg = Settings(MONITOR_INTERVAL_SECONDS=0)
        errors = validate_settings(cfg)
        assert any("MONITOR_INTERVAL_SECONDS must be positive" in e for e in errors)

    def test_negative_retry_count_detected(self):
        cfg = Settings(MONITOR_MAX_RETRIES=-1)
        errors = validate_settings(cfg)
        assert any("MONITOR_MAX_RETRIES must be >= 0" in e for e in errors)

    def test_zero_or_negative_retention_days_detected(self):
        cfg = Settings(SCRAPE_RUN_RETENTION_DAYS=0)
        errors = validate_settings(cfg)
        assert any("SCRAPE_RUN_RETENTION_DAYS must be at least 1 day" in e for e in errors)

    def test_invalid_smtp_configuration_detected(self):
        cfg = Settings(EMAIL_BACKEND="smtp", SMTP_ENABLED=True, SMTP_HOST="")
        errors = validate_settings(cfg)
        assert any("SMTP_HOST must be specified" in e for e in errors)

    def test_validation_error_raised(self):
        cfg = Settings(MONITOR_INTERVAL_SECONDS=-50)
        with pytest.raises(ConfigurationValidationError) as exc_info:
            assert_valid_settings(cfg)
        assert "MONITOR_INTERVAL_SECONDS must be positive" in str(exc_info.value)
