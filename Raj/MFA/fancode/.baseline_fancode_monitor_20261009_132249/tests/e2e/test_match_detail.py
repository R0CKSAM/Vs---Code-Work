"""
test_match_detail.py – Playwright automated E2E tests for FanCode Match Detail Scraper.
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
from app.scraper.match_detail.models import RawMatchDetail
from app.scraper.match_detail.parser import MatchDetailParser
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper
from tests.fixtures.match_detail import SAMPLE_MATCH_DETAIL_NORMAL


class TestFanCodeMatchDetailPlaywrightE2E:
    def test_match_detail_enrichment_logic(self, browser: Browser) -> None:
        """Verify enrichment preserves fields and updates record."""
        init_db()
        with get_session() as session:
            repo = MatchesRepository(session)
            m = repo.upsert(
                external_id="match-e2e-501",
                title="E2E Initial Match",
                slug="e2e-initial",
                source_url="https://www.fancode.com/matches/e2e-initial",
                venue="Initial Stadium",
                status="UPCOMING",
            )
            orig_id = m.id

        scraper = FanCodeMatchDetailScraper(browser=browser)
        # Parse fixture with updated details
        detail = MatchDetailParser.parse_detail(
            RawMatchDetail(raw_data=SAMPLE_MATCH_DETAIL_NORMAL),
            default_url="https://www.fancode.com/matches/e2e-initial",
        )
        assert detail is not None
        detail.match_external_id = "match-e2e-501"
        scraper._enrich_in_database(detail)

        with get_session() as session:
            repo = MatchesRepository(session)
            enriched = repo.get_by_id(orig_id)
            assert enriched is not None
            assert enriched.id == orig_id
            assert enriched.title == "Mumbai Indians vs Chennai Super Kings"

    def test_live_match_detail_smoke_navigation(self, page: Page) -> None:
        """Smoke test navigating to live schedule and opening first available match link."""
        page.goto(
            settings.SCHEDULE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        # Find first match link if available
        links = page.locator('a[href*="/matches/"], a[href*="/match/"]')
        if links.count() > 0:
            href = links.first.get_attribute("href")
            if href:
                target_url = href if href.startswith("http") else f"https://www.fancode.com{href}"
                resp = page.goto(target_url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)
                assert resp is not None
                assert resp.status in range(200, 400)
                assert not page.is_closed()
        else:
            # If no live match links on schedule page, pass gracefully
            assert not page.is_closed()
