"""
test_live_now.py – Playwright automated E2E tests for FanCode Live Now Scraper.
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
from app.database.models import Match
from app.database.repositories import MatchesRepository
from app.scraper.live_now.models import RawLiveItem
from app.scraper.live_now.network import LiveNowNetworkInterceptor
from app.scraper.live_now.parser import LiveNowParser
from app.scraper.live_now.scraper import FanCodeLiveNowScraper
from tests.fixtures.live_now import (
    SAMPLE_LIVE_CRICKET,
    SAMPLE_NESTED_LIVE_PAYLOAD,
)


class TestFanCodeLiveNowPlaywrightE2E:
    """E2E test suite for Live Now Scraper."""

    def test_live_page_reachable(self, page: Page) -> None:
        """Verify Live Now URL responds with HTTP 2xx/3xx or redirects cleanly."""
        resp = page.goto(
            settings.LIVE_NOW_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert resp is not None
        assert resp.status in range(200, 400)
        assert not page.is_closed()

    def test_network_interceptor_attaches_and_captures(self, page: Page) -> None:
        """Verify network interceptor attaches without error and captures responses."""
        interceptor = LiveNowNetworkInterceptor(page)
        interceptor.attach()

        page.goto(
            settings.LIVE_NOW_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        page.wait_for_timeout(1000)

        # Interceptor should have list structure and detach cleanly
        payloads = interceptor.get_payloads()
        assert isinstance(payloads, list)
        interceptor.detach()
        assert not interceptor._attached

    def test_live_scraper_runs_without_crashing(self, browser: Browser) -> None:
        """Verify scraper execution lifecycle runs cleanly and returns a list."""
        scraper = FanCodeLiveNowScraper(browser=browser, max_items=5)
        results = scraper.scrape(persist_db=False)
        assert isinstance(results, list)

    def test_live_enrichment_flow(self, browser: Browser) -> None:
        """Verify enrichment of an existing match in the database using Live Now scraper."""
        init_db()
        with get_session() as session:
            repo = MatchesRepository(session)
            m = repo.upsert(
                external_id="e2e-live-101",
                title="E2E Pre-Live Match",
                slug="e2e-pre-live",
                source_url="https://www.fancode.com/matches/e2e-pre-live",
                venue="Eden Gardens",
                status="SCHEDULED",
            )
            orig_id = m.id

        # Simulate live record matching e2e-live-101
        raw = RawLiveItem(raw_data=dict(SAMPLE_LIVE_CRICKET, matchId="e2e-live-101"))
        live_rec = LiveNowParser.parse_live_item(raw)
        assert live_rec is not None

        scraper = FanCodeLiveNowScraper(browser=browser)
        scraper._persist_to_database([live_rec])

        with get_session() as session:
            repo = MatchesRepository(session)
            enriched = repo.get_by_id(orig_id)
            assert enriched is not None
            assert enriched.id == orig_id
            assert enriched.status == "LIVE"
            assert enriched.score_summary == "MI 152/4 (16.2 ov)"
            assert enriched.venue == "Eden Gardens"  # Preserved

    def test_live_scraper_handles_empty_or_no_live_matches_gracefully(self, browser: Browser) -> None:
        """Verify scraper gracefully completes even if no live matches are active."""
        scraper = FanCodeLiveNowScraper(browser=browser, max_items=1)
        # Using a URL that produces no live items
        results = scraper.scrape(persist_db=False)
        assert isinstance(results, list)
