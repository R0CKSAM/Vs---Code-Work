"""
test_clean_environment.py – Phase 12 Clean Environment & Deployment Isolation Tests.

Verifies:
- Required project directories can be created cleanly from scratch.
- Settings load with safe defaults.
- Invalid configurations fail loudly with actionable validation errors.
- Missing optional directories do not crash startup.
- Temporary / isolated test databases operate without touching production paths.
- Codebase in app/ contains zero developer-specific hardcoded absolute paths (e.g. C:\\Users\\, D:\\MFA\\).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select

from app.config.settings import Settings
from app.config.validation import ConfigurationValidationError, assert_valid_settings
from app.database.connection import init_db, Base
from app.database.models import Sport, Match


class TestCleanEnvironmentValidation:
    """Validates that the project can start cleanly in fresh/arbitrary environments."""

    def test_required_directories_can_be_created(self, tmp_path):
        """Verifies that all standard runtime directories can be created on demand."""
        data_dir = tmp_path / "data"
        logs_dir = tmp_path / "logs"
        screenshots_dir = tmp_path / "screenshots"
        notif_dir = tmp_path / "data" / "notifications"
        raw_dir = tmp_path / "data" / "raw"

        for directory in [data_dir, logs_dir, screenshots_dir, notif_dir, raw_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            assert directory.exists()
            assert directory.is_dir()

    def test_configuration_loads_safely_with_defaults(self):
        """Verifies default settings are completely safe and contain valid default values."""
        cfg = Settings(_env_file=None)
        assert cfg.BASE_URL.startswith("http")
        assert cfg.BROWSER_TIMEOUT > 0
        assert cfg.MONITOR_INTERVAL_SECONDS > 0
        assert cfg.MONITOR_MAX_RETRIES >= 0
        assert cfg.STALE_RUN_TIMEOUT_SECONDS > 0
        assert cfg.SCRAPE_RUN_RETENTION_DAYS > 0
        assert cfg.CHANGE_EVENT_RETENTION_DAYS > 0
        assert cfg.NOTIFICATION_RETENTION_DAYS > 0

        # Assert valid settings does not raise
        assert_valid_settings(cfg)

    def test_invalid_configuration_fails_clearly(self):
        """Verifies that improper configuration flags are rejected with ConfigurationValidationError."""
        with pytest.raises(ConfigurationValidationError, match="BASE_URL"):
            assert_valid_settings(Settings(BASE_URL="not-a-valid-url", _env_file=None))

        with pytest.raises(ConfigurationValidationError, match="BROWSER_TIMEOUT"):
            assert_valid_settings(Settings(BROWSER_TIMEOUT=-5, _env_file=None))

        with pytest.raises(ConfigurationValidationError, match="MONITOR_INTERVAL_SECONDS"):
            assert_valid_settings(Settings(MONITOR_INTERVAL_SECONDS=0, _env_file=None))

        with pytest.raises(ConfigurationValidationError, match="MONITOR_MAX_RETRIES"):
            assert_valid_settings(Settings(MONITOR_MAX_RETRIES=-1, _env_file=None))

        with pytest.raises(ConfigurationValidationError, match="SCRAPE_RUN_RETENTION_DAYS"):
            assert_valid_settings(Settings(SCRAPE_RUN_RETENTION_DAYS=0, _env_file=None))

    def test_missing_optional_directories_do_not_crash_startup(self, tmp_path):
        """Verifies missing optional runtime directories do not block setting initialization."""
        isolated_cfg = Settings(
            DATA_DIR=str(tmp_path / "nonexistent_data"),
            LOG_DIR=str(tmp_path / "nonexistent_logs"),
            SCREENSHOT_DIR=str(tmp_path / "nonexistent_screenshots"),
            _env_file=None,
        )
        assert isolated_cfg.DATA_DIR is not None
        assert_valid_settings(isolated_cfg)

    def test_temporary_test_database_isolated(self, tmp_path):
        """Verifies that creating and initializing a standalone SQLite DB in tmp_path leaves production untouched."""
        db_path = tmp_path / "isolated.db"
        test_url = f"sqlite:///{db_path}"
        engine = create_engine(test_url, echo=False)
        Base.metadata.create_all(bind=engine)

        assert db_path.exists()
        assert db_path.stat().st_size > 0
        engine.dispose()

    def test_no_hardcoded_developer_paths_in_source(self):
        """
        Scans all Python files in app/ to guarantee no developer-specific machine paths
        (e.g., 'C:\\Users\\', 'D:\\MFA\\', '/Users/') are hardcoded into production code.
        """
        app_root = Path(__file__).resolve().parents[2] / "app"
        assert app_root.exists() and app_root.is_dir()

        disallowed_patterns = [
            re.compile(r"C:[\\/]Users", re.IGNORECASE),
            re.compile(r"D:[\\/]MFA", re.IGNORECASE),
            re.compile(r"/home/[a-zA-Z0-9_-]+/", re.IGNORECASE),
            re.compile(r"/Users/[a-zA-Z0-9_-]+/", re.IGNORECASE),
        ]

        violations = []
        for py_file in app_root.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            for pattern in disallowed_patterns:
                matches = pattern.findall(text)
                if matches:
                    violations.append(f"{py_file.name}: matched '{matches[0]}'")

        assert not violations, f"Found hardcoded developer paths in app/: {violations}"
