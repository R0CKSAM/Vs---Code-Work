"""
scraper.py – FanCode Tours / Series Scraper.

Discovers tournaments, tours, and competitions via:
1. Navigation / tour / series links on FanCode
2. Public API JSON payloads
3. DOM extraction of series / tour cards
Associates with sports and existing match records.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Browser, Page
from sqlalchemy import select

from app.config.settings import settings
from app.database.connection import get_session, init_db
from app.database.models import Match
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.schedule.network import ScheduleNetworkInterceptor
from app.scraper.tours.models import TourRecord
from app.scraper.tours.normalizer import derive_tour_slug
from app.scraper.tours.parser import ToursParser

logger = logging.getLogger(__name__)


class FanCodeToursScraper:
    """Scrapes and registers tours, series, and tournaments from FanCode."""

    def __init__(
        self,
        browser: Browser,
        tours_url: Optional[str] = None,
        max_items: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        save_raw: Optional[bool] = None,
    ) -> None:
        self.browser = browser
        self.tours_url = tours_url or settings.TOURS_URL
        self.max_items = max_items or settings.TOUR_MAX_ITEMS
        self.timeout_seconds = timeout_seconds or settings.TOUR_TIMEOUT_SECONDS
        self.save_raw = save_raw if save_raw is not None else settings.TOUR_SAVE_RAW

    def scrape(self, persist_db: bool = True) -> List[TourRecord]:
        logger.info("Tours scrape started | URL: %s", self.tours_url)
        run_id: Optional[int] = None

        if persist_db:
            init_db()
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                run = runs_repo.create_run(run_type="tours", metadata_json={"url": self.tours_url})
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

        discovered_tours: List[TourRecord] = []
        errors_count = 0
        error_msg: Optional[str] = None

        try:
            page.goto(
                self.tours_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_seconds * 1000,
            )
            page.wait_for_timeout(settings.TOUR_WAIT_AFTER_LOAD_MS)

            # 1. Inspect captured JSON payloads
            payloads = interceptor.get_payloads()
            for p in payloads:
                parsed = ToursParser.extract_tours_from_json(p["data"])
                discovered_tours.extend(parsed)

            # 2. Extract from DOM links
            dom_tours = self._extract_tours_from_dom(page)
            discovered_tours.extend(dom_tours)

        except Exception as exc:
            logger.error("Tours scrape navigation error: %s", exc)
            error_msg = str(exc)
            errors_count += 1
        finally:
            interceptor.detach()
            try:
                page.close()
                context.close()
            except Exception:
                pass

        # Deduplicate tours
        deduped: List[TourRecord] = []
        seen = set()
        for t in discovered_tours[:self.max_items]:
            key = t.external_id or t.source_url or t.slug
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        # 3. Database Persistence & Match Linkage
        if persist_db and run_id is not None:
            created, updated = self._persist_tours(deduped)
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

    def _extract_tours_from_dom(self, page: Page) -> List[TourRecord]:
        items: List[TourRecord] = []
        try:
            links = page.locator('a[href*="/tour/"], a[href*="/tours/"], a[href*="/series/"]').all()
            for a in links[:self.max_items]:
                try:
                    href = a.get_attribute("href")
                    text = a.inner_text().strip()
                    if href and text:
                        norm = normalize_url(href, page.url) or href
                        name = text.split("\n")[0].strip()
                        slug = derive_tour_slug(name)
                        items.append(TourRecord(
                            name=name,
                            slug=slug,
                            source_url=norm,
                        ))
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("DOM tour extraction error: %s", exc)
        return items

    def _persist_tours(self, tours: List[TourRecord]) -> tuple[int, int]:
        created = 0
        updated = 0
        with get_session() as session:
            sports_repo = SportsRepository(session)
            tours_repo = ToursRepository(session)

            for t in tours:
                sport_id = None
                if t.sport_name:
                    sport = sports_repo.upsert(
                        name=t.sport_name,
                        slug=t.sport_slug or "sport",
                        external_id=t.sport_external_id,
                        source_url=f"https://www.fancode.com/{t.sport_slug}" if t.sport_slug else "https://www.fancode.com",
                    )
                    sport_id = sport.id

                existing = None
                if t.external_id:
                    existing = tours_repo.get_by_external_id(t.external_id)
                if not existing and t.slug:
                    existing = tours_repo.get_by_slug(t.slug)
                if not existing and t.source_url:
                    existing = tours_repo.get_by_source_url(t.source_url)

                saved_tour = tours_repo.upsert(
                    external_id=t.external_id,
                    sport_id=sport_id,
                    name=t.name,
                    slug=t.slug,
                    source_url=t.source_url,
                    description=t.description,
                    image_url=t.image_url,
                    start_date=t.start_date,
                    end_date=t.end_date,
                    status=t.status,
                )

                if existing:
                    updated += 1
                else:
                    created += 1

                # Attempt to link unassociated matches that reference this tour's slug or name
                self._link_matches_to_tour(session, saved_tour)

        return created, updated

    def _link_matches_to_tour(self, session, tour) -> None:
        """Associate existing matches where match source_url or slug contains tour slug."""
        try:
            stmt = select(Match).where(Match.tour_id.is_(None))
            unlinked = session.scalars(stmt).all()
            for m in unlinked:
                if tour.slug in m.source_url or (m.slug and tour.slug in m.slug):
                    m.tour_id = tour.id
        except Exception as exc:
            logger.debug("Error linking matches to tour: %s", exc)
