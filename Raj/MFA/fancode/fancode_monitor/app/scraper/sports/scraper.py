"""
scraper.py – FanCode Sports Scraper.

Discovers available sports via:
1. Navigation / category links on FanCode
2. Public API JSON payloads
3. DOM extraction of sport category elements
Persists records to the sports table via SportsRepository.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Browser, Page

from app.config.settings import settings
from app.database.connection import get_session, init_db
from app.database.repositories import ScrapeRunsRepository, SportsRepository
from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.network import ScheduleNetworkInterceptor
from app.scraper.sports.models import SportRecord
from app.scraper.sports.normalizer import derive_sport_slug
from app.scraper.sports.parser import SportsParser

logger = logging.getLogger(__name__)

# Known primary sport routes on FanCode
KNOWN_SPORT_SECTIONS = [
    ("Cricket", "cricket", "https://www.fancode.com/cricket"),
    ("Football", "football", "https://www.fancode.com/football"),
    ("Formula 1", "formula-1", "https://www.fancode.com/sports/formula-1-19762"),
    ("Tennis", "tennis", "https://www.fancode.com/tennis"),
    ("MotoGP", "motogp", "https://www.fancode.com/sports/motogp"),
    ("Golf", "golf", "https://www.fancode.com/sports/golf"),
    ("Motorsports", "motorsports", "https://www.fancode.com/sports/motorsports-19763"),
    ("Badminton", "badminton", "https://www.fancode.com/badminton"),
    ("Kabaddi", "kabaddi", "https://www.fancode.com/kabaddi"),
    ("Basketball", "basketball", "https://www.fancode.com/basketball"),
    ("Hockey", "hockey", "https://www.fancode.com/hockey"),
]


class FanCodeSportsScraper:
    """Scrapes and registers sports categories from FanCode."""

    def __init__(
        self,
        browser: Browser,
        sports_url: Optional[str] = None,
        max_items: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        save_raw: Optional[bool] = None,
    ) -> None:
        self.browser = browser
        self.sports_url = sports_url or settings.SPORTS_URL
        self.max_items = max_items or settings.SPORT_MAX_ITEMS
        self.timeout_seconds = timeout_seconds or settings.SPORT_TIMEOUT_SECONDS
        self.save_raw = save_raw if save_raw is not None else settings.SPORT_SAVE_RAW

    def scrape(self, persist_db: bool = True) -> List[SportRecord]:
        logger.info("Sports scrape started | URL: %s", self.sports_url)
        run_id: Optional[int] = None

        if persist_db:
            init_db()
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                run = runs_repo.create_run(run_type="sports", metadata_json={"url": self.sports_url})
                run_id = run.id

        context = self.browser.new_context(
            viewport={
                "width": settings.BROWSER_VIEWPORT_WIDTH,
                "height": settings.BROWSER_VIEWPORT_HEIGHT,
            },
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        interceptor = ScheduleNetworkInterceptor(page)
        interceptor.attach()

        discovered_sports: List[SportRecord] = []
        errors_count = 0
        error_msg: Optional[str] = None

        try:
            page.goto(
                self.sports_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_seconds * 1000,
            )
            page.wait_for_timeout(settings.SPORT_WAIT_AFTER_LOAD_MS)

            # 1. Inspect captured JSON payloads
            payloads = interceptor.get_payloads()
            for p in payloads:
                parsed = SportsParser.extract_sports_from_json(p["data"])
                discovered_sports.extend(parsed)

            # 2. Extract from DOM navigation links
            dom_sports = self._extract_sports_from_dom(page)
            discovered_sports.extend(dom_sports)

            # 3. Include known primary sports if nothing found
            if not discovered_sports:
                for name, slug, url in KNOWN_SPORT_SECTIONS:
                    discovered_sports.append(SportRecord(
                        name=name,
                        slug=slug,
                        source_url=url,
                    ))

        except Exception as exc:
            logger.error("Sports scrape navigation error: %s", exc)
            error_msg = str(exc)
            errors_count += 1
        finally:
            interceptor.detach()
            try:
                page.close()
                context.close()
            except Exception:
                pass

        # Deduplicate sports
        deduped: List[SportRecord] = []
        seen = set()
        for s in discovered_sports[:self.max_items]:
            key = s.external_id or s.slug
            if key not in seen:
                seen.add(key)
                deduped.append(s)

        # 4. Database Persistence
        if persist_db and run_id is not None:
            created, updated = self._persist_sports(deduped)
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                runs_repo.finish_run(
                    run_id=run_id,
                    status="success" if not error_msg else "partial",
                    records_processed=len(deduped),
                    records_created=created,
                    records_updated=updated,
                    errors_count=errors_count,
                    error_message=error_msg,
                )

        return deduped

    def _extract_sports_from_dom(self, page: Page) -> List[SportRecord]:
        items: List[SportRecord] = []
        try:
            # Query navigation links to sport paths
            for name, slug, expected_url in KNOWN_SPORT_SECTIONS:
                loc = page.locator(f'a[href*="/{slug}"]')
                if loc.count() > 0:
                    href = loc.first.get_attribute("href")
                    norm_url = normalize_url(href, page.url) if href else expected_url
                    items.append(SportRecord(
                        name=name,
                        slug=slug,
                        source_url=norm_url or expected_url,
                    ))
        except Exception as exc:
            logger.debug("DOM sports extraction error: %s", exc)
        return items

    def _persist_sports(self, sports: List[SportRecord]) -> tuple[int, int]:
        created = 0
        updated = 0
        with get_session() as session:
            repo = SportsRepository(session)
            for s in sports:
                existing = None
                if s.external_id:
                    existing = repo.get_by_external_id(s.external_id)
                if not existing and s.slug:
                    existing = repo.get_by_slug(s.slug)

                repo.upsert(
                    external_id=s.external_id,
                    name=s.name,
                    slug=s.slug,
                    source_url=s.source_url,
                    description=s.description,
                    image_url=s.image_url,
                    is_active=s.is_active,
                )
                if existing:
                    updated += 1
                else:
                    created += 1
        return created, updated
