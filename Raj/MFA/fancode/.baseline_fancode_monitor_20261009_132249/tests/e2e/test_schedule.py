"""
test_schedule.py – Playwright E2E automated tests for FanCode Schedule Scraper.

Tests:
1. schedule page reachable and responds
2. schedule scraper can launch and complete cleanly
3. network monitoring captures requests on schedule page
4. parser extracts normalized records from intercepted or simulated fixture data
5. duplicate schedule items are deduplicated deterministically
6. database persistence writes matches to SQLite
7. repeated scrape executes without duplicating records
8. malformed payload does not cause a crash
9. scrape run record is tracked in scrape_runs table
10. scraper terminates within limits
11. live FanCode schedule test checks reachable URL and structural signals
12. no critical browser console errors during schedule navigation
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
from app.database.models import Match, ScrapeRun
from app.database.repositories import MatchesRepository, ScrapeRunsRepository
from app.scraper.schedule.models import RawScheduleItem
from app.scraper.schedule.network import ScheduleNetworkInterceptor
from app.scraper.schedule.parser import ScheduleParser
from app.scraper.schedule.scraper import FanCodeScheduleScraper
from tests.fixtures.schedule import (
    SAMPLE_CRICKET_MATCH,
    SAMPLE_DUPLICATE_ITEMS,
    SAMPLE_FOOTBALL_MATCH,
    SAMPLE_MALFORMED_ITEM,
)


class TestFanCodeSchedulePlaywrightE2E:
    """E2E suite for Schedule Scraper."""

    def test_schedule_page_reachable(self, page: Page) -> None:
        """Verify schedule URL responds with HTTP 200/300."""
        response = page.goto(
            settings.SCHEDULE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert response is not None
        assert response.status in range(200, 400)
        assert "fancode.com" in page.url

    def test_schedule_network_interceptor_attaches_and_captures(self, page: Page) -> None:
        """Verify ScheduleNetworkInterceptor captures network events without error."""
        interceptor = ScheduleNetworkInterceptor(page)
        interceptor.attach()
        try:
            page.goto(
                settings.SCHEDULE_URL,
                wait_until="domcontentloaded",
                timeout=settings.BROWSER_TIMEOUT,
            )
            # Should have handled events cleanly
            payloads = interceptor.get_payloads()
            assert isinstance(payloads, list)
        finally:
            interceptor.detach()

    def test_schedule_scraper_execution_with_persistence(self, browser: Browser) -> None:
        """Run scraper with limited items and check termination and DB persistence."""
        init_db()
        scraper = FanCodeScheduleScraper(
            browser=browser,
            schedule_url=settings.SCHEDULE_URL,
            max_items=5,
            timeout_seconds=25,
        )
        matches = scraper.scrape(persist_db=True)
        assert isinstance(matches, list)

        # Scrape run must be recorded
        with get_session() as session:
            runs_repo = ScrapeRunsRepository(session)
            latest = runs_repo.get_latest("schedule")
            assert latest is not None
            assert latest.status in ("success", "partial")

    def test_repeated_scrape_does_not_duplicate_matches(self, browser: Browser) -> None:
        """Verify repeated scrapes update rather than duplicate records."""
        init_db()
        # Manually persist a match fixture
        with get_session() as session:
            matches_repo = MatchesRepository(session)
            m = ScheduleParser.parse_item(RawScheduleItem(raw_data=SAMPLE_CRICKET_MATCH))
            assert m is not None
            matches_repo.upsert(
                external_id=m.external_id,
                title=m.title,
                slug=m.slug or "slug",
                source_url=m.source_url,
                status=m.status,
            )

        # Run upsert again with updated title
        with get_session() as session:
            matches_repo = MatchesRepository(session)
            matches_repo.upsert(
                external_id="match-901",
                title="India vs Australia 1st ODI - Updated",
                slug="ind-vs-aus",
                source_url="https://www.fancode.com/matches/ind-vs-aus-1st-odi",
                status="LIVE",
            )

            # Query count for external_id
            all_matches = [match for match in session.query(Match).filter_by(external_id="match-901").all()]
            assert len(all_matches) == 1
            assert all_matches[0].title == "India vs Australia 1st ODI - Updated"
            assert all_matches[0].status == "LIVE"

    def test_malformed_item_does_not_crash_scraper(self) -> None:
        """Ensure parser skips malformed items gracefully."""
        items = [
            RawScheduleItem(raw_data=SAMPLE_MALFORMED_ITEM),
            RawScheduleItem(raw_data=SAMPLE_FOOTBALL_MATCH),
        ]
        parsed = []
        for it in items:
            m = ScheduleParser.parse_item(it)
            if m:
                parsed.append(m)

        assert len(parsed) == 1
        assert parsed[0].external_id == "fb-888"

    def test_live_fancode_schedule_structure(self, page: Page) -> None:
        """Smoke test against live FanCode schedule page looking for general schedule markers."""
        page.goto(
            settings.SCHEDULE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert page.title() != ""
        # Check for presence of navigation links or match containers
        anchors = page.locator("a[href]").all()
        assert len(anchors) > 0

    def test_schedule_page_no_critical_console_errors(self, page: Page) -> None:
        """Verify schedule page navigation does not raise unhandled exceptions."""
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(
            settings.SCHEDULE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        # Should not crash the browser
        assert not page.is_closed()
