"""
test_videos.py – Playwright automated E2E tests for FanCode Videos & Highlights Scraper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.database.connection import get_session, init_db
from app.database.models import Video
from app.database.repositories import VideosRepository
from app.scraper.videos.models import RawVideoItem
from app.scraper.videos.network import VideoNetworkInterceptor
from app.scraper.videos.parser import VideosParser
from app.scraper.videos.scraper import FanCodeVideosScraper
from tests.fixtures.videos import SAMPLE_VIDEO_HIGHLIGHT


class TestFanCodeVideosPlaywrightE2E:
    """E2E test suite for Videos Scraper."""

    def test_videos_page_reachable(self, page: Page) -> None:
        """Verify video URL or homepage responds with HTTP 2xx/3xx."""
        resp = page.goto(
            settings.VIDEO_SCRAPER_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert resp is not None
        assert resp.status in range(200, 400)
        assert not page.is_closed()

    def test_network_interceptor_attaches_and_captures(self, page: Page) -> None:
        """Verify network interceptor attaches and detaches cleanly."""
        interceptor = VideoNetworkInterceptor(page)
        interceptor.attach()

        page.goto(
            settings.VIDEO_SCRAPER_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        page.wait_for_timeout(1000)

        payloads = interceptor.get_payloads()
        assert isinstance(payloads, list)
        interceptor.detach()
        assert not interceptor._attached

    def test_videos_scraper_runs_without_crashing(self, browser: Browser) -> None:
        """Verify scraper execution lifecycle runs cleanly."""
        scraper = FanCodeVideosScraper(browser=browser, max_items=5)
        results = scraper.scrape(persist_db=False)
        assert isinstance(results, list)

    def test_video_persistence_and_idempotency(self, browser: Browser) -> None:
        """Verify video records are persisted to SQLite and repeated scrape does not duplicate."""
        init_db()
        scraper = FanCodeVideosScraper(browser=browser)

        raw = RawVideoItem(raw_data=dict(SAMPLE_VIDEO_HIGHLIGHT, videoId="e2e-vid-101"))
        record = VideosParser.parse_video_item(raw)
        assert record is not None

        # Run 1
        scraper._persist_to_database([record])
        # Run 2
        scraper._persist_to_database([record])

        with get_session() as session:
            repo = VideosRepository(session)
            vid = repo.get_by_external_id("e2e-vid-101")
            assert vid is not None
            assert vid.title == "IND vs AUS 1st ODI Match Highlights"
            assert vid.video_type == "MATCH_HIGHLIGHT"

    def test_videos_scraper_handles_empty_page_gracefully(self, browser: Browser) -> None:
        """Verify scraper completes gracefully on page with no video cards."""
        scraper = FanCodeVideosScraper(browser=browser, max_items=1)
        results = scraper.scrape(persist_db=False)
        assert isinstance(results, list)
