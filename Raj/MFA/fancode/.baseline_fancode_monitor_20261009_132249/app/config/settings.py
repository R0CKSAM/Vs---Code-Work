"""
FanCode Monitor - Application Settings
Phase 0: Project Foundation
Phase 1: Discovery Engine

All settings are driven by environment variables (via .env or shell).
Pydantic-Settings is used for validation and type coercion.
"""

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the FanCode Monitor application.

    Values are loaded in priority order:
      1. Environment variables
      2. .env file (if present)
      3. Defaults defined here
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Target website
    # ------------------------------------------------------------------ #
    BASE_URL: str = "https://www.fancode.com"

    # ------------------------------------------------------------------ #
    # Browser / Playwright
    # ------------------------------------------------------------------ #
    BROWSER_HEADLESS: bool = True
    BROWSER_SLOW_MO: int = 0           # milliseconds between actions (0 = off)
    BROWSER_TIMEOUT: int = 30_000      # default navigation timeout (ms)
    BROWSER_VIEWPORT_WIDTH: int = 1280
    BROWSER_VIEWPORT_HEIGHT: int = 720

    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #
    SCREENSHOT_DIR: str = "screenshots"
    LOG_DIR: str = "logs"
    DATA_DIR: str = "data"

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------ #
    # Phase 9 – Alerting & Notification Engine
    # ------------------------------------------------------------------ #
    NOTIFICATION_ENABLED: bool = True
    EMAIL_BACKEND: str = "console"       # "console", "test", "smtp"
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 15
    ALERT_EMAIL_FROM: str = "alerts@fancode-monitor.local"
    ALERT_EMAIL_TO: str = "admin@fancode-monitor.local"
    ALERT_EMAIL_CC: str = ""
    ALERT_EMAIL_BCC: str = ""
    ALERT_RECIPIENTS: str = ""           # comma-separated list or fallback for ALERT_EMAIL_TO
    NOTIFICATION_MAX_EVENTS_PER_BATCH: int = 100
    NOTIFICATION_OUTPUT_DIR: str = "data/notifications"

    # ------------------------------------------------------------------ #
    # Phase 10 – Scheduler & Continuous Monitoring Engine
    # ------------------------------------------------------------------ #
    MONITOR_ENABLED: bool = True
    MONITOR_INTERVAL_SECONDS: int = 300
    MONITOR_RUN_TIMEOUT_SECONDS: int = 900
    MONITOR_STAGE_TIMEOUT_SECONDS: int = 300
    MONITOR_MAX_RETRIES: int = 1
    MONITOR_RETRY_DELAY_SECONDS: float = 2.0
    MONITOR_LOCK_ENABLED: bool = True
    MONITOR_LOCK_FILE: str = "data/monitor.lock"
    MONITOR_LOCK_TIMEOUT_SECONDS: int = 1800
    MONITOR_NOTIFICATION_ENABLED: bool = True
    SCRAPE_INTERVAL_MINUTES: int = 60

    # ------------------------------------------------------------------ #
    # Phase 11 – Hardening, Observability & Data Maintenance
    # ------------------------------------------------------------------ #
    STALE_RUN_TIMEOUT_SECONDS: int = 1800
    SCRAPE_RUN_RETENTION_DAYS: int = 30
    CHANGE_EVENT_RETENTION_DAYS: int = 90
    NOTIFICATION_RETENTION_DAYS: int = 90
    HEARTBEAT_FILE: str = "data/monitor.heartbeat"
    HEARTBEAT_INTERVAL_SECONDS: int = 15
    LOG_STRUCTURED: bool = False


    # ------------------------------------------------------------------ #
    # Phase 1 – Discovery Engine
    # ------------------------------------------------------------------ #
    DISCOVERY_MAX_DEPTH: int = 2            # crawl depth from homepage
    DISCOVERY_MAX_PAGES: int = 30           # hard cap on pages visited
    DISCOVERY_MAX_LINKS_PER_PAGE: int = 50  # links extracted per page
    DISCOVERY_TIMEOUT_SECONDS: int = 120    # total discovery wall-clock limit
    DISCOVERY_PAGE_TIMEOUT_MS: int = 30_000 # per-page navigation timeout
    DISCOVERY_WAIT_AFTER_LOAD_MS: int = 2_000  # extra settle time after DOMContentLoaded
    REQUEST_DELAY_SECONDS: float = 1.5      # polite delay between page visits
    DISCOVERY_OUTPUT_DIR: str = "data/raw/discovery"  # artifact output path

    # ------------------------------------------------------------------ #
    # Phase 2 – Database & Persistence Layer
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = "sqlite:///data/fancode.db"
    DATABASE_ECHO: bool = False

    # ------------------------------------------------------------------ #
    # Phase 3 – Schedule Scraper
    # ------------------------------------------------------------------ #
    SCHEDULE_URL: str = "https://www.fancode.com/schedule"
    SCHEDULE_MAX_ITEMS: int = 100
    SCHEDULE_MAX_PAGES: int = 5
    SCHEDULE_TIMEOUT_SECONDS: int = 60
    SCHEDULE_WAIT_AFTER_LOAD_MS: int = 3_000
    SCHEDULE_REQUEST_DELAY_SECONDS: float = 1.0
    SCHEDULE_SAVE_RAW: bool = False
    SCHEDULE_RAW_DIR: str = "data/raw/schedule"
    SCHEDULE_DAYS_AHEAD: int = 7
    # ------------------------------------------------------------------ #
    # Phase 4 – Sports & Tours Scraper
    # ------------------------------------------------------------------ #
    SPORTS_URL: str = "https://www.fancode.com"
    SPORT_MAX_ITEMS: int = 50
    SPORT_TIMEOUT_SECONDS: int = 45
    SPORT_WAIT_AFTER_LOAD_MS: int = 2_000
    SPORT_REQUEST_DELAY_SECONDS: float = 1.0
    SPORT_SAVE_RAW: bool = False
    SPORT_RAW_DIR: str = "data/raw/sports"

    TOURS_URL: str = "https://www.fancode.com"
    TOUR_MAX_ITEMS: int = 50
    TOUR_MAX_PAGES: int = 3
    TOUR_TIMEOUT_SECONDS: int = 45
    TOUR_WAIT_AFTER_LOAD_MS: int = 2_000
    TOUR_REQUEST_DELAY_SECONDS: float = 1.0
    TOUR_SAVE_RAW: bool = False
    TOUR_RAW_DIR: str = "data/raw/tours"

    # ------------------------------------------------------------------ #
    # Phase 5 – Match Detail Scraper & Enrichment
    # ------------------------------------------------------------------ #
    MATCH_DETAIL_TIMEOUT_SECONDS: int = 45
    MATCH_DETAIL_WAIT_AFTER_LOAD_MS: int = 2_000
    MATCH_DETAIL_MAX_ITEMS: int = 20
    MATCH_DETAIL_REQUEST_DELAY_SECONDS: float = 1.0
    MATCH_DETAIL_SAVE_RAW: bool = False
    MATCH_DETAIL_RAW_DIR: str = "data/raw/match_detail"

    # ------------------------------------------------------------------ #
    # Phase 6 – Live Now Scraper
    # ------------------------------------------------------------------ #
    LIVE_NOW_URL: str = "https://www.fancode.com/live-now/all-sports"
    LIVE_NOW_TIMEOUT_SECONDS: int = 45
    LIVE_NOW_WAIT_AFTER_LOAD_MS: int = 2_000
    LIVE_NOW_MAX_ITEMS: int = 50
    LIVE_NOW_REQUEST_DELAY_SECONDS: float = 1.0
    LIVE_NOW_SAVE_RAW: bool = False
    LIVE_NOW_RAW_DIR: str = "data/raw/live_now"

    # ------------------------------------------------------------------ #
    # Phase 7 – Videos & Highlights Scraper
    # ------------------------------------------------------------------ #
    VIDEO_SCRAPER_URL: str = "https://www.fancode.com/video"
    VIDEO_SCRAPER_TIMEOUT_SECONDS: int = 45
    VIDEO_SCRAPER_WAIT_AFTER_LOAD_MS: int = 2_000
    VIDEO_SCRAPER_MAX_ITEMS: int = 50
    VIDEO_SCRAPER_REQUEST_DELAY_SECONDS: float = 1.0
    VIDEO_SCRAPER_SAVE_RAW: bool = False
    VIDEO_SCRAPER_RAW_DIR: str = "data/raw/videos"

    @field_validator("BASE_URL")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")



# Singleton instance used throughout the application
settings = Settings()
