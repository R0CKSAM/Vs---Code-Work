"""
scraper.py – FanCode Schedule Scraper.

Lifecycle:
1. Initialize Playwright Browser / Context
2. Attach network response interceptor
3. Navigate to https://www.fancode.com/schedule
4. Wait for React/Next.js hydration
5. Extract structured schedule items from intercepted JSON payloads
6. If structured payloads are empty, fallback to rendered DOM card extraction
7. Normalize all matches to ScheduleMatch entities
8. Persist records to matches, sports, and tours tables via Phase 2 repositories
9. Record scrape metrics into scrape_runs table
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError as PWTimeout

from app.config.settings import settings
from app.database.connection import get_session, init_db, utc_now
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.scraper.schedule.models import RawScheduleItem, ScheduleMatch
from app.scraper.schedule.network import ScheduleNetworkInterceptor
from app.scraper.schedule.parser import ScheduleParser

logger = logging.getLogger(__name__)


class FanCodeScheduleScraper:
    """End-to-end scraper for FanCode schedule fixtures."""

    def __init__(
        self,
        browser: Browser,
        schedule_url: Optional[str] = None,
        max_items: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        save_raw: Optional[bool] = None,
    ) -> None:
        self.browser = browser
        self.schedule_url = schedule_url or settings.SCHEDULE_URL
        self.max_items = max_items or settings.SCHEDULE_MAX_ITEMS
        self.timeout_seconds = timeout_seconds or settings.SCHEDULE_TIMEOUT_SECONDS
        self.save_raw = save_raw if save_raw is not None else settings.SCHEDULE_SAVE_RAW

    def scrape(self, persist_db: bool = True) -> List[ScheduleMatch]:
        """
        Execute schedule scrape.
        Returns a list of parsed and normalized ScheduleMatch objects.
        """
        logger.info("Schedule scrape started | URL: %s", self.schedule_url)
        run_id: Optional[int] = None

        if persist_db:
            init_db()
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                run = runs_repo.create_run(run_type="schedule", metadata_json={"url": self.schedule_url})
                run_id = run.id

        context = self.browser.new_context(
            viewport={
                "width": settings.BROWSER_VIEWPORT_WIDTH,
                "height": settings.BROWSER_VIEWPORT_HEIGHT,
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        interceptor = ScheduleNetworkInterceptor(page)
        interceptor.attach()

        raw_items: List[RawScheduleItem] = []
        errors_count = 0
        error_msg: Optional[str] = None

        urls_to_scrape = [self.schedule_url]
        for extra_url in [
            "https://www.fancode.com/sports/formula-1-19762/matches",
            "https://www.fancode.com/sports/motorsports-19763/matches",
            "https://www.fancode.com/sports/motogp/matches",
            "https://www.fancode.com/sports/golf",
        ]:
            if extra_url not in urls_to_scrape:
                urls_to_scrape.append(extra_url)

        try:
            for target_url in urls_to_scrape:
                logger.info("Navigating to %s", target_url)
                try:
                    page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_seconds * 1000,
                    )
                    page.wait_for_timeout(settings.SCHEDULE_WAIT_AFTER_LOAD_MS)
                except Exception as nav_exc:
                    logger.debug("Failed loading %s: %s", target_url, nav_exc)
                    continue

                # 1. Inspect captured network responses for JSON match data
                payloads = interceptor.get_payloads()
                logger.info("Captured %d candidate network payloads from %s", len(payloads), target_url)

                page_raw = []
                for p in payloads:
                    extracted = ScheduleParser.extract_raw_items_from_json(p["data"])
                    page_raw.extend(extracted)
                    if self.save_raw:
                        self._save_raw_payload(p)

                # 2. DOM fallback if no structured JSON matches were found on this page
                if not page_raw:
                    logger.info("No JSON match items found on %s; attempting DOM fallback.", target_url)
                    page_raw = self._extract_from_dom(page)

                raw_items.extend(page_raw)

        except Exception as exc:
            logger.error("Schedule scrape navigation error: %s", exc)
            error_msg = str(exc)
            errors_count += 1
        finally:
            interceptor.detach()
            try:
                page.close()
                context.close()
            except Exception:
                pass

        # 3. Parse and normalize
        normalized_matches: List[ScheduleMatch] = []
        seen_identities = set()

        for raw in raw_items[:self.max_items]:
            try:
                match = ScheduleParser.parse_item(raw)
                if match:
                    identity = match.external_id or match.source_url or match.slug
                    if identity not in seen_identities:
                        seen_identities.add(identity)
                        normalized_matches.append(match)
            except Exception as exc:
                logger.warning("Error parsing raw schedule item: %s", exc)
                errors_count += 1

        logger.info("Extracted and normalized %d schedule matches", len(normalized_matches))

        # 4. Database Persistence
        if persist_db and run_id is not None:
            created, updated = self._persist_matches(normalized_matches)
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                runs_repo.finish_run(
                    run_id=run_id,
                    status="success" if not error_msg else "partial",
                    records_processed=len(normalized_matches),
                    records_created=created,
                    records_updated=updated,
                    errors_count=errors_count,
                    error_message=error_msg,
                )

        return normalized_matches

    def _extract_from_dom(self, page: Page) -> List[RawScheduleItem]:
        """Extract visible match/schedule cards from rendered HTML."""
        items: List[RawScheduleItem] = []
        try:
            # Query card-like containers or anchor links to match details
            match_links = page.locator('a[href*="/matches/"], a[href*="/match/"], a[href*="/video/"], a[href*="/sports/"]').all()
            for link in match_links[:self.max_items]:
                try:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()
                    if text:
                        items.append(RawScheduleItem(
                            raw_data={
                                "title": text.split("\n")[0],
                                "url": href,
                            },
                            source_type="dom",
                        ))
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("DOM fallback extraction error: %s", exc)
        return items

    def _persist_matches(self, matches: List[ScheduleMatch]) -> tuple[int, int]:
        """Upsert sports, tours, and matches using Phase 2 repositories."""
        created_count = 0
        updated_count = 0

        with get_session() as session:
            sports_repo = SportsRepository(session)
            tours_repo = ToursRepository(session)
            matches_repo = MatchesRepository(session)

            for m in matches:
                # 1. Sport relationship
                sport_id = None
                if m.sport_name:
                    sport = sports_repo.upsert(
                        name=m.sport_name,
                        slug=m.sport_slug or "sport",
                        external_id=m.sport_external_id,
                        source_url=f"https://www.fancode.com/{m.sport_slug}" if m.sport_slug else "https://www.fancode.com",
                    )
                    sport_id = sport.id

                # 2. Tour relationship
                tour_id = None
                if m.tour_name:
                    tour = tours_repo.upsert(
                        name=m.tour_name,
                        slug=m.tour_slug or "tour",
                        external_id=m.tour_external_id,
                        sport_id=sport_id,
                        source_url=f"https://www.fancode.com/tours/{m.tour_slug}" if m.tour_slug else "https://www.fancode.com",
                    )
                    tour_id = tour.id

                # 3. Match upsert
                existing = None
                if m.external_id:
                    existing = matches_repo.get_by_external_id(m.external_id)
                if not existing and m.source_url:
                    existing = matches_repo.get_by_source_url(m.source_url)

                matches_repo.upsert(
                    external_id=m.external_id,
                    tour_id=tour_id,
                    sport_id=sport_id,
                    title=m.title,
                    slug=m.slug or "match",
                    source_url=m.source_url,
                    match_date=m.match_date,
                    start_time=m.start_time,
                    status=m.status,
                    venue=m.venue,
                    team_a_name=m.team_a_name,
                    team_a_external_id=m.team_a_external_id,
                    team_a_logo_url=m.team_a_logo_url,
                    team_b_name=m.team_b_name,
                    team_b_external_id=m.team_b_external_id,
                    team_b_logo_url=m.team_b_logo_url,
                    image_url=m.image_url,
                    score_summary=m.score_summary,
                )

                if existing:
                    updated_count += 1
                else:
                    created_count += 1

        return created_count, updated_count

    def _save_raw_payload(self, payload: dict) -> None:
        try:
            raw_dir = Path(settings.SCHEDULE_RAW_DIR)
            raw_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filepath = raw_dir / f"payload_{ts}.json"
            filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save raw schedule payload: %s", exc)
