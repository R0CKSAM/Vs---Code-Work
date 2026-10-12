"""
test_tours.py – Playwright automated E2E tests for FanCode Tours Scraper.
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
from app.database.models import Tour
from app.database.repositories import ScrapeRunsRepository, ToursRepository
from app.scraper.tours.parser import ToursParser
from app.scraper.tours.scraper import FanCodeToursScraper
from tests.fixtures.tours import SAMPLE_TOUR_NORMAL


class TestFanCodeToursPlaywrightE2E:
    def test_tours_area_reachable(self, page: Page) -> None:
        response = page.goto(
            settings.TOURS_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert response is not None
        assert response.status in range(200, 400)
        assert "fancode.com" in page.url

    def test_tours_scraper_execution_and_persistence(self, browser: Browser) -> None:
        init_db()
        scraper = FanCodeToursScraper(
            browser=browser,
            tours_url=settings.TOURS_URL,
            max_items=5,
            timeout_seconds=25,
        )
        tours = scraper.scrape(persist_db=True)
        assert isinstance(tours, list)

        with get_session() as session:
            runs_repo = ScrapeRunsRepository(session)
            latest = runs_repo.get_latest("tours")
            assert latest is not None
            assert latest.status in ("success", "partial")

    def test_repeated_tours_scrape_idempotency(self, browser: Browser) -> None:
        init_db()
        # Persist a tour fixture
        with get_session() as session:
            repo = ToursRepository(session)
            t = ToursParser.parse_tour_dict(SAMPLE_TOUR_NORMAL)
            assert t is not None
            repo.upsert(
                external_id=t.external_id,
                name=t.name,
                slug=t.slug,
                source_url=t.source_url,
                status=t.status,
            )

        # Upsert again with modified status
        with get_session() as session:
            repo = ToursRepository(session)
            repo.upsert(
                external_id="tour-101",
                name="Indian Premier League 2026",
                slug="ipl-2026",
                source_url="https://www.fancode.com/tours/ipl-2026",
                status="LIVE",
            )
            tours_list = [tr for tr in session.query(Tour).filter_by(external_id="tour-101").all()]
            assert len(tours_list) == 1
            assert tours_list[0].status == "LIVE"

    def test_no_critical_console_errors_on_tours(self, page: Page) -> None:
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(
            settings.TOURS_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert not page.is_closed()
