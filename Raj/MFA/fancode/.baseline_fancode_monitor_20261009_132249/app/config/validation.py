"""
validation.py – Comprehensive Configuration Validation for FanCode Monitor (Phase 11).

Validates application settings on startup and CLI invocation, rejecting invalid,
negative, or inconsistent values while redacting secrets from all error messages.
"""

from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse

from app.config.settings import Settings, settings


class ConfigurationValidationError(ValueError):
    """Raised when configuration validation fails."""
    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        message = "Configuration validation failed:\n  - " + "\n  - ".join(errors)
        super().__init__(message)


def validate_settings(cfg: Optional[Settings] = None) -> List[str]:
    """
    Validates a Settings instance.
    Returns a list of validation error messages (empty list if valid).
    Never exposes passwords, tokens, or secrets.
    """
    c = cfg or settings
    errors: List[str] = []

    # 1. URLs
    urls_to_check = [
        ("BASE_URL", c.BASE_URL),
        ("SCHEDULE_URL", c.SCHEDULE_URL),
        ("SPORTS_URL", c.SPORTS_URL),
        ("TOURS_URL", c.TOURS_URL),
        ("LIVE_NOW_URL", c.LIVE_NOW_URL),
        ("VIDEO_SCRAPER_URL", c.VIDEO_SCRAPER_URL),
    ]
    for name, u in urls_to_check:
        if not u:
            errors.append(f"{name} must not be empty.")
            continue
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"{name} must be a valid HTTP/HTTPS URL (got: '{u[:30]}...').")

    # 2. Timeouts (must be > 0)
    positive_timeouts = [
        ("BROWSER_TIMEOUT", c.BROWSER_TIMEOUT),
        ("MONITOR_RUN_TIMEOUT_SECONDS", c.MONITOR_RUN_TIMEOUT_SECONDS),
        ("MONITOR_STAGE_TIMEOUT_SECONDS", c.MONITOR_STAGE_TIMEOUT_SECONDS),
        ("MONITOR_LOCK_TIMEOUT_SECONDS", c.MONITOR_LOCK_TIMEOUT_SECONDS),
        ("DISCOVERY_TIMEOUT_SECONDS", c.DISCOVERY_TIMEOUT_SECONDS),
        ("SCHEDULE_TIMEOUT_SECONDS", c.SCHEDULE_TIMEOUT_SECONDS),
        ("SPORT_TIMEOUT_SECONDS", c.SPORT_TIMEOUT_SECONDS),
        ("TOUR_TIMEOUT_SECONDS", c.TOUR_TIMEOUT_SECONDS),
        ("MATCH_DETAIL_TIMEOUT_SECONDS", c.MATCH_DETAIL_TIMEOUT_SECONDS),
        ("LIVE_NOW_TIMEOUT_SECONDS", c.LIVE_NOW_TIMEOUT_SECONDS),
        ("VIDEO_SCRAPER_TIMEOUT_SECONDS", c.VIDEO_SCRAPER_TIMEOUT_SECONDS),
        ("STALE_RUN_TIMEOUT_SECONDS", c.STALE_RUN_TIMEOUT_SECONDS),
    ]
    for name, val in positive_timeouts:
        if val <= 0:
            errors.append(f"{name} must be positive (> 0, got: {val}).")

    # 3. Intervals (must be > 0)
    positive_intervals = [
        ("MONITOR_INTERVAL_SECONDS", c.MONITOR_INTERVAL_SECONDS),
        ("SCRAPE_INTERVAL_MINUTES", c.SCRAPE_INTERVAL_MINUTES),
        ("HEARTBEAT_INTERVAL_SECONDS", c.HEARTBEAT_INTERVAL_SECONDS),
    ]
    for name, val in positive_intervals:
        if val <= 0:
            errors.append(f"{name} must be positive (> 0, got: {val}).")

    # 4. Retries (must be >= 0)
    if c.MONITOR_MAX_RETRIES < 0:
        errors.append(f"MONITOR_MAX_RETRIES must be >= 0 (got: {c.MONITOR_MAX_RETRIES}).")
    if c.MONITOR_RETRY_DELAY_SECONDS < 0:
        errors.append(f"MONITOR_RETRY_DELAY_SECONDS must be >= 0 (got: {c.MONITOR_RETRY_DELAY_SECONDS}).")

    # 5. Retention periods (must be >= 1)
    retention_periods = [
        ("SCRAPE_RUN_RETENTION_DAYS", c.SCRAPE_RUN_RETENTION_DAYS),
        ("CHANGE_EVENT_RETENTION_DAYS", c.CHANGE_EVENT_RETENTION_DAYS),
        ("NOTIFICATION_RETENTION_DAYS", c.NOTIFICATION_RETENTION_DAYS),
    ]
    for name, val in retention_periods:
        if val < 1:
            errors.append(f"{name} must be at least 1 day (got: {val}).")

    # 6. Database
    if not c.DATABASE_URL:
        errors.append("DATABASE_URL must not be empty.")

    # 7. Notification settings
    if c.NOTIFICATION_ENABLED:
        if c.EMAIL_BACKEND not in ("console", "test", "smtp"):
            errors.append(f"EMAIL_BACKEND must be 'console', 'test', or 'smtp' (got: '{c.EMAIL_BACKEND}').")
        if c.EMAIL_BACKEND == "smtp" or c.SMTP_ENABLED:
            if not c.SMTP_HOST:
                errors.append("SMTP_HOST must be specified when SMTP email backend is enabled.")
            if c.SMTP_PORT <= 0 or c.SMTP_PORT > 65535:
                errors.append(f"SMTP_PORT must be between 1 and 65535 (got: {c.SMTP_PORT}).")
            if not c.ALERT_EMAIL_FROM:
                errors.append("ALERT_EMAIL_FROM must not be empty when SMTP email backend is enabled.")

    # 8. Log level
    if c.LOG_LEVEL.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        errors.append(f"LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL (got: '{c.LOG_LEVEL}').")

    return errors


def assert_valid_settings(cfg: Optional[Settings] = None) -> None:
    """Validates settings and raises ConfigurationValidationError if any error exists."""
    errors = validate_settings(cfg)
    if errors:
        raise ConfigurationValidationError(errors)
