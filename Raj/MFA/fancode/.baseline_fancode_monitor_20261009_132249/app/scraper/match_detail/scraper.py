"""
scraper.py – FanCode Match Detail Scraper & Enrichment Engine.

Loads match detail pages, captures public network / embedded state,
normalizes extracted attributes, and enriches existing database matches
without overwriting good data with None.
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
from app.scraper.match_detail.models import MatchDetail, RawMatchDetail
from app.scraper.match_detail.parser import MatchDetailParser
from app.scraper.schedule.network import ScheduleNetworkInterceptor

logger = logging.getLogger(__name__)


class FanCodeMatchDetailScraper:
    """Enriches existing Match records with detailed attributes."""

    def __init__(
        self,
        browser: Browser,
        timeout_seconds: Optional[int] = None,
        save_raw: Optional[bool] = None,
    ) -> None:
        self.browser = browser
        self.timeout_seconds = timeout_seconds or settings.MATCH_DETAIL_TIMEOUT_SECONDS
        self.save_raw = save_raw if save_raw is not None else settings.MATCH_DETAIL_SAVE_RAW

    def enrich_match_by_url(self, match_url: str, persist_db: bool = True) -> Optional[MatchDetail]:
        """Scrape a single match detail page and optionally enrich DB."""
        context = self.browser.new_context(
            viewport={"width": settings.BROWSER_VIEWPORT_WIDTH, "height": settings.BROWSER_VIEWPORT_HEIGHT},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        interceptor = ScheduleNetworkInterceptor(page)
        interceptor.attach()

        detail_record: Optional[MatchDetail] = None
        try:
            logger.info("Opening match detail page: %s", match_url)
            page.goto(match_url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
            page.wait_for_timeout(settings.MATCH_DETAIL_WAIT_AFTER_LOAD_MS)

            # 1. Check intercepted JSON responses
            payloads = interceptor.get_payloads()
            for p in payloads:
                candidate = MatchDetailParser.parse_detail(
                    RawMatchDetail(raw_data=p["data"], source_type="json"),
                    default_url=match_url,
                )
                if candidate and (candidate.title or candidate.match_external_id):
                    detail_record = candidate
                    break

            # 2. Check embedded state in page HTML
            if not detail_record:
                html = page.content()
                embedded = MatchDetailParser.extract_embedded_json(html)
                if embedded:
                    candidate = MatchDetailParser.parse_detail(
                        RawMatchDetail(raw_data=embedded, source_type="embedded"),
                        default_url=match_url,
                    )
                    if candidate:
                        detail_record = candidate

            # 3. DOM Fallback
            if not detail_record:
                detail_record = self._extract_from_dom(page, match_url)

        except Exception as exc:
            logger.error("Error scraping match detail %s: %s", match_url, exc)
        finally:
            interceptor.detach()
            try:
                page.close()
                context.close()
            except Exception:
                pass

        if detail_record and persist_db:
            self._enrich_in_database(detail_record)

        return detail_record

    def enrich_batch(self, limit: int = 10, persist_db: bool = True) -> List[MatchDetail]:
        """Batch-enrich existing database matches missing venue, tour, or details."""
        init_db()
        target_matches: List[Match] = []
        with get_session() as session:
            stmt = select(Match).order_by(Match.updated_at.asc()).limit(limit)
            target_matches = list(session.scalars(stmt).all())

        results: List[MatchDetail] = []
        errors_count = 0
        run_id = None

        if persist_db:
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                run = runs_repo.create_run(run_type="match_detail", metadata_json={"batch_size": len(target_matches)})
                run_id = run.id

        for m in target_matches:
            try:
                url = m.source_url
                res = self.enrich_match_by_url(url, persist_db=persist_db)
                if res:
                    results.append(res)
            except Exception as exc:
                logger.warning("Failed enriching match %s: %s", m.id, exc)
                errors_count += 1

        if persist_db and run_id:
            with get_session() as session:
                runs_repo = ScrapeRunsRepository(session)
                runs_repo.finish_run(
                    run_id=run_id,
                    status="success" if errors_count == 0 else "partial",
                    records_processed=len(target_matches),
                    records_updated=len(results),
                    errors_count=errors_count,
                )

        return results

    def _extract_from_dom(self, page: Page, source_url: str) -> MatchDetail:
        """Extract visible details from rendered page."""
        title = page.title()
        return MatchDetail(
            source_url=source_url,
            title=title.split("|")[0].strip() if "|" in title else title,
        )

    def _enrich_in_database(self, detail: MatchDetail) -> None:
        """
        Merge new attributes into existing Match without overwriting non-null values with None.
        """
        with get_session() as session:
            matches_repo = MatchesRepository(session)
            sports_repo = SportsRepository(session)
            tours_repo = ToursRepository(session)

            # Find existing match
            existing = None
            if detail.match_external_id:
                existing = matches_repo.get_by_external_id(detail.match_external_id)
            if not existing and detail.source_url:
                existing = matches_repo.get_by_source_url(detail.source_url)

            # Associate sport if found
            sport_id = None
            if detail.sport_name:
                sport = sports_repo.upsert(
                    name=detail.sport_name,
                    slug=detail.sport_name.lower().replace(" ", "-"),
                    external_id=detail.sport_external_id,
                    source_url=f"https://www.fancode.com/{detail.sport_name.lower()}",
                )
                sport_id = sport.id

            # Associate tour if found
            tour_id = None
            if detail.tour_name:
                tour = tours_repo.upsert(
                    name=detail.tour_name,
                    slug=detail.tour_name.lower().replace(" ", "-"),
                    external_id=detail.tour_external_id,
                    sport_id=sport_id,
                    source_url=f"https://www.fancode.com/tours/{detail.tour_name.lower().replace(' ', '-')}",
                )
                tour_id = tour.id

            if existing:
                # Backfill external_id if missing and discovered from detail
                if not existing.external_id and detail.match_external_id and str(detail.match_external_id).strip():
                    existing.external_id = str(detail.match_external_id).strip()

                # Merge fields: only update if detail field is NOT None
                if detail.title is not None:
                    existing.title = detail.title
                if detail.venue is not None:
                    existing.venue = detail.venue
                if detail.status is not None:
                    existing.status = detail.status
                if detail.match_date is not None:
                    existing.match_date = detail.match_date
                if detail.start_time is not None:
                    existing.start_time = detail.start_time
                if detail.team_a_name is not None:
                    existing.team_a_name = detail.team_a_name
                if detail.team_b_name is not None:
                    existing.team_b_name = detail.team_b_name
                if detail.team_a_logo_url is not None:
                    existing.team_a_logo_url = detail.team_a_logo_url
                if detail.team_b_logo_url is not None:
                    existing.team_b_logo_url = detail.team_b_logo_url
                if detail.score_summary is not None:
                    existing.score_summary = detail.score_summary
                if detail.image_url is not None:
                    existing.image_url = detail.image_url
                if sport_id is not None and existing.sport_id is None:
                    existing.sport_id = sport_id
                if tour_id is not None and existing.tour_id is None:
                    existing.tour_id = tour_id

                existing.last_seen_at = datetime.now(timezone.utc)
                existing.updated_at = datetime.now(timezone.utc)
                session.flush()
            else:
                # If not existing, insert as new match
                matches_repo.upsert(
                    external_id=detail.match_external_id,
                    source_url=detail.source_url,
                    title=detail.title or "Match",
                    slug=detail.slug or "match",
                    venue=detail.venue,
                    status=detail.status or "UNKNOWN",
                    match_date=detail.match_date,
                    start_time=detail.start_time,
                    team_a_name=detail.team_a_name,
                    team_b_name=detail.team_b_name,
                    team_a_logo_url=detail.team_a_logo_url,
                    team_b_logo_url=detail.team_b_logo_url,
                    score_summary=detail.score_summary,
                    image_url=detail.image_url,
                    sport_id=sport_id,
                    tour_id=tour_id,
                )
