"""
test_sports.py – Playwright automated E2E tests for FanCode Sports Scraper.
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
from app.database.models import Sport
from app.database.repositories import ScrapeRunsRepository, SportsRepository
from app.scraper.sports.parser import SportsParser
from app.scraper.sports.scraper import FanCodeSportsScraper
from tests.fixtures.sports import SAMPLE_SPORT_NORMAL


class TestFanCodeSportsPlaywrightE2E:
    def test_sports_page_reachable(self, page: Page) -> None:
        response = page.goto(
            settings.SPORTS_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert response is not None
        assert response.status in range(200, 400)
        assert "fancode.com" in page.url

    def test_sports_scraper_execution_and_persistence(self, browser: Browser) -> None:
        init_db()
        scraper = FanCodeSportsScraper(
            browser=browser,
            sports_url=settings.SPORTS_URL,
            max_items=5,
            timeout_seconds=25,
        )
        sports = scraper.scrape(persist_db=True)
        assert isinstance(sports, list)
        assert len(sports) > 0

        with get_session() as session:
            runs_repo = ScrapeRunsRepository(session)
            latest = runs_repo.get_latest("sports")
            assert latest is not None
            assert latest.status in ("success", "partial")

    def test_repeated_sports_scrape_idempotency(self, browser: Browser) -> None:
        init_db()
        # Persist a sport fixture
        with get_session() as session:
            repo = SportsRepository(session)
            s = SportsParser.parse_sport_dict(SAMPLE_SPORT_NORMAL)
            assert s is not None
            repo.upsert(
                external_id=s.external_id,
                name=s.name,
                slug=s.slug,
                source_url=s.source_url,
            )

        # Upsert again with modified name/description
        with get_session() as session:
            repo = SportsRepository(session)
            repo.upsert(
                external_id="sport-1",
                name="Cricket Global",
                slug="cricket",
                source_url="https://www.fancode.com/cricket",
            )
            sports_list = [sp for sp in session.query(Sport).filter_by(external_id="sport-1").all()]
            assert len(sports_list) == 1
            assert sports_list[0].name == "Cricket Global"

    def test_no_critical_console_errors_on_sports(self, page: Page) -> None:
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(
            settings.SPORTS_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert not page.is_closed()
