"""
test_settings.py – Unit tests for the Settings configuration module.

These tests run without a browser and verify that pydantic-settings
correctly parses environment variables and applies defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import Settings  # noqa: E402


class TestSettingsDefaults:
    """Verify default values when no environment overrides are provided."""

    def setup_method(self) -> None:
        """Create a fresh Settings instance with no env overrides."""
        self.cfg = Settings()

    def test_base_url_default(self) -> None:
        assert self.cfg.BASE_URL == "https://www.fancode.com"

    def test_base_url_no_trailing_slash(self) -> None:
        cfg = Settings(BASE_URL="https://www.fancode.com/")
        assert not cfg.BASE_URL.endswith("/"), "BASE_URL must not have a trailing slash"

    def test_headless_default(self) -> None:
        assert self.cfg.BROWSER_HEADLESS is True

    def test_timeout_positive(self) -> None:
        assert self.cfg.BROWSER_TIMEOUT > 0

    def test_viewport_positive(self) -> None:
        assert self.cfg.BROWSER_VIEWPORT_WIDTH > 0
        assert self.cfg.BROWSER_VIEWPORT_HEIGHT > 0

    def test_scrape_interval_positive(self) -> None:
        assert self.cfg.SCRAPE_INTERVAL_MINUTES > 0

    def test_log_level_is_string(self) -> None:
        assert isinstance(self.cfg.LOG_LEVEL, str)
        assert self.cfg.LOG_LEVEL.upper() in (
            "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        )


class TestSettingsOverrides:
    """Verify that keyword-argument overrides work correctly."""

    def test_override_base_url(self) -> None:
        cfg = Settings(BASE_URL="https://staging.fancode.com")
        assert cfg.BASE_URL == "https://staging.fancode.com"

    def test_override_headless_false(self) -> None:
        cfg = Settings(BROWSER_HEADLESS=False)
        assert cfg.BROWSER_HEADLESS is False

    def test_override_timeout(self) -> None:
        cfg = Settings(BROWSER_TIMEOUT=60_000)
        assert cfg.BROWSER_TIMEOUT == 60_000

    def test_override_slow_mo(self) -> None:
        cfg = Settings(BROWSER_SLOW_MO=500)
        assert cfg.BROWSER_SLOW_MO == 500

    def test_discovery_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.DISCOVERY_MAX_DEPTH == 2
        assert cfg.DISCOVERY_MAX_PAGES == 30
        assert cfg.DISCOVERY_MAX_LINKS_PER_PAGE == 50
        assert cfg.DISCOVERY_TIMEOUT_SECONDS == 120
        assert cfg.REQUEST_DELAY_SECONDS == 1.5

    def test_discovery_settings_overrides(self) -> None:
        cfg = Settings(
            DISCOVERY_MAX_DEPTH=3,
            DISCOVERY_MAX_PAGES=15,
            REQUEST_DELAY_SECONDS=0.5,
        )
        assert cfg.DISCOVERY_MAX_DEPTH == 3
        assert cfg.DISCOVERY_MAX_PAGES == 15
        assert cfg.REQUEST_DELAY_SECONDS == 0.5

    def test_database_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.DATABASE_URL == "sqlite:///data/fancode.db"
        assert cfg.DATABASE_ECHO is False

    def test_database_settings_overrides(self) -> None:
        cfg = Settings(
            DATABASE_URL="sqlite:///:memory:",
            DATABASE_ECHO=True,
        )
        assert cfg.DATABASE_URL == "sqlite:///:memory:"
        assert cfg.DATABASE_ECHO is True

    def test_schedule_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.SCHEDULE_URL == "https://www.fancode.com/schedule"
        assert cfg.SCHEDULE_MAX_ITEMS == 100
        assert cfg.SCHEDULE_MAX_PAGES == 5
        assert cfg.SCHEDULE_TIMEOUT_SECONDS == 60
        assert cfg.SCHEDULE_WAIT_AFTER_LOAD_MS == 3000
        assert cfg.SCHEDULE_REQUEST_DELAY_SECONDS == 1.0
        assert cfg.SCHEDULE_SAVE_RAW is False
        assert cfg.SCHEDULE_DAYS_AHEAD == 7

    def test_schedule_settings_overrides(self) -> None:
        cfg = Settings(
            SCHEDULE_MAX_ITEMS=50,
            SCHEDULE_DAYS_AHEAD=3,
            SCHEDULE_SAVE_RAW=True,
        )
        assert cfg.SCHEDULE_MAX_ITEMS == 50
        assert cfg.SCHEDULE_DAYS_AHEAD == 3
        assert cfg.SCHEDULE_SAVE_RAW is True

    def test_sports_and_tours_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.SPORTS_URL == "https://www.fancode.com"
        assert cfg.SPORT_MAX_ITEMS == 50
        assert cfg.SPORT_TIMEOUT_SECONDS == 45
        assert cfg.TOURS_URL == "https://www.fancode.com"
        assert cfg.TOUR_MAX_ITEMS == 50
        assert cfg.TOUR_MAX_PAGES == 3

    def test_sports_and_tours_settings_overrides(self) -> None:
        cfg = Settings(
            SPORT_MAX_ITEMS=20,
            TOUR_MAX_ITEMS=10,
            TOUR_SAVE_RAW=True,
        )
        assert cfg.SPORT_MAX_ITEMS == 20
        assert cfg.TOUR_MAX_ITEMS == 10
        assert cfg.TOUR_SAVE_RAW is True

    def test_match_detail_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.MATCH_DETAIL_TIMEOUT_SECONDS == 45
        assert cfg.MATCH_DETAIL_WAIT_AFTER_LOAD_MS == 2000
        assert cfg.MATCH_DETAIL_MAX_ITEMS == 20
        assert cfg.MATCH_DETAIL_SAVE_RAW is False

    def test_match_detail_settings_overrides(self) -> None:
        cfg = Settings(
            MATCH_DETAIL_TIMEOUT_SECONDS=60,
            MATCH_DETAIL_MAX_ITEMS=5,
            MATCH_DETAIL_SAVE_RAW=True,
        )
        assert cfg.MATCH_DETAIL_TIMEOUT_SECONDS == 60
        assert cfg.MATCH_DETAIL_MAX_ITEMS == 5
        assert cfg.MATCH_DETAIL_SAVE_RAW is True

    def test_live_now_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.LIVE_NOW_URL == "https://www.fancode.com/live"
        assert cfg.LIVE_NOW_TIMEOUT_SECONDS == 45
        assert cfg.LIVE_NOW_WAIT_AFTER_LOAD_MS == 2000
        assert cfg.LIVE_NOW_MAX_ITEMS == 50
        assert cfg.LIVE_NOW_SAVE_RAW is False

    def test_live_now_settings_overrides(self) -> None:
        cfg = Settings(
            LIVE_NOW_URL="https://www.fancode.com/live-now",
            LIVE_NOW_TIMEOUT_SECONDS=60,
            LIVE_NOW_MAX_ITEMS=10,
            LIVE_NOW_SAVE_RAW=True,
        )
        assert cfg.LIVE_NOW_URL == "https://www.fancode.com/live-now"
        assert cfg.LIVE_NOW_TIMEOUT_SECONDS == 60
        assert cfg.LIVE_NOW_MAX_ITEMS == 10
        assert cfg.LIVE_NOW_SAVE_RAW is True

    def test_video_scraper_settings_defaults(self) -> None:
        cfg = Settings()
        assert cfg.VIDEO_SCRAPER_URL == "https://www.fancode.com/video"
        assert cfg.VIDEO_SCRAPER_TIMEOUT_SECONDS == 45
        assert cfg.VIDEO_SCRAPER_WAIT_AFTER_LOAD_MS == 2000
        assert cfg.VIDEO_SCRAPER_MAX_ITEMS == 50
        assert cfg.VIDEO_SCRAPER_SAVE_RAW is False

    def test_video_scraper_settings_overrides(self) -> None:
        cfg = Settings(
            VIDEO_SCRAPER_URL="https://www.fancode.com/videos",
            VIDEO_SCRAPER_TIMEOUT_SECONDS=30,
            VIDEO_SCRAPER_MAX_ITEMS=15,
            VIDEO_SCRAPER_SAVE_RAW=True,
        )
        assert cfg.VIDEO_SCRAPER_URL == "https://www.fancode.com/videos"
        assert cfg.VIDEO_SCRAPER_TIMEOUT_SECONDS == 30
        assert cfg.VIDEO_SCRAPER_MAX_ITEMS == 15
        assert cfg.VIDEO_SCRAPER_SAVE_RAW is True







