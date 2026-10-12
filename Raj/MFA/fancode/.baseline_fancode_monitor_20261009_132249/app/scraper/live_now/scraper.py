"""
scraper.py – FanCode Live Now Scraper & Live-State Acquisition Engine.

Navigates to FanCode's live portal, captures structured live match/event payloads,
extracts real-time score summaries and live statuses, and enriches existing matches
in the database while preventing duplicate creation and field erasure.
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
from app.database.connection import get_session, init_db, utc_now
from app.database.models import Match
from app.database.repositories import (
    MatchesRepository,
    ScrapeRunsRepository,
    SportsRepository,
    ToursRepository,
)
from app.scraper.discovery.url_normalizer import normalize as normalize_url
from app.scraper.live_now.models import LiveMatchRecord, RawLiveItem
from app.scraper.live_now.network import LiveNowNetworkInterceptor
from app.scraper.live_now.normalizer import (
    LiveNowNormalizer,
    clean_match_external_id,
    extract_match_id_from_url,
    extract_title_from_slug_or_url,
    has_sufficient_match_identity,
    is_valid_match_title,
    is_vs_title,
)
from app.scraper.live_now.parser import LiveNowParser
from app.scraper.schedule.normalizer import derive_slug

logger = logging.getLogger(__name__)


class FanCodeLiveNowScraper:
    """End-to-end scraper for current FanCode Live Now fixtures."""

    def __init__(
        self,
        browser: Browser,
        live_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_items: Optional[int] = None,
        save_raw: Optional[bool] = None,
    ) -> None:
        self.browser = browser
        self.live_url = live_url or settings.LIVE_NOW_URL
        self.timeout_seconds = timeout_seconds or settings.LIVE_NOW_TIMEOUT_SECONDS
        self.max_items = max_items or settings.LIVE_NOW_MAX_ITEMS
        self.save_raw = save_raw if save_raw is not None else settings.LIVE_NOW_SAVE_RAW

    def scrape(self, persist_db: bool = True) -> List[LiveMatchRecord]:
        """Scrape live fixtures, optionally enriching database records."""
        context = self.browser.new_context(
            viewport={"width": settings.BROWSER_VIEWPORT_WIDTH, "height": settings.BROWSER_VIEWPORT_HEIGHT},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        interceptor = LiveNowNetworkInterceptor(page)
        interceptor.attach()

        urls_to_try = [self.live_url]
        for alt in [
            "https://www.fancode.com/live-now/all-sports",
            "https://www.fancode.com/live-now",
            f"{settings.SCHEDULE_URL}?tab=live",
        ]:
            if alt not in urls_to_try:
                urls_to_try.append(alt)

        raw_candidates: List[RawLiveItem] = []
        try:
            for url in urls_to_try:
                logger.info("Opening Live Now page: %s", url)
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
                    page.wait_for_timeout(settings.LIVE_NOW_WAIT_AFTER_LOAD_MS)
                except Exception as exc:
                    logger.debug("Failed loading %s: %s", url, exc)
                    continue

                if resp and resp.status >= 400:
                    continue

                # 1. Process intercepted JSON responses
                payloads = interceptor.get_payloads()
                if self.save_raw and payloads:
                    self._save_raw_payloads(payloads)

                for p in payloads:
                    items = LiveNowParser.extract_live_items_from_payload(p["data"])
                    raw_candidates.extend(items)

                # 2. Check embedded Next.js SSR state if network items were empty
                if not raw_candidates:
                    html = page.content()
                    embedded = LiveNowParser.extract_embedded_json(html)
                    if embedded:
                        items = LiveNowParser.extract_live_items_from_payload(embedded)
                        raw_candidates.extend(items)

                # 3. DOM Fallback
                if not raw_candidates:
                    dom_items = self._extract_from_dom(page)
                    raw_candidates.extend(dom_items)

                if raw_candidates:
                    break

        except Exception as exc:
            logger.error("Error scraping Live Now page: %s", exc)
        finally:
            interceptor.detach()
            try:
                page.close()
                context.close()
            except Exception:
                pass

        # Parse candidates
        parsed_records: List[LiveMatchRecord] = []
        for raw in raw_candidates:
            rec = LiveNowParser.parse_live_item(raw, default_url=self.live_url)
            if rec:
                parsed_records.append(rec)

        # Deduplicate
        unique_records = LiveNowNormalizer.deduplicate_records(parsed_records)

        # Cap items
        if self.max_items and len(unique_records) > self.max_items:
            unique_records = unique_records[: self.max_items]

        # Persist / Enrich
        if persist_db:
            self._persist_to_database(unique_records)

        return unique_records

    def _extract_from_dom(self, page: Page) -> List[RawLiveItem]:
        """Extract live cards from rendered DOM."""
        dom_items: List[RawLiveItem] = []
        try:
            cards = page.locator(
                'a[href*="/matches/"], a[href*="/match/"], [data-testid*="match"], .match-card, [class*="Card"], article'
            )
            count = min(cards.count(), self.max_items or 30)

            for i in range(count):
                el = cards.nth(i)
                text = el.inner_text().strip()
                href = el.get_attribute("href") or ""
                if not text and not href:
                    continue

                # Skip links that are purely landing page or navigation URLs
                if href:
                    normalized_href = href.lower()
                    if normalized_href in (
                        "/live",
                        "/live-now",
                        "/live-now/all-sports",
                        "https://www.fancode.com/live-now/all-sports",
                        "https://www.fancode.com/live-now",
                        "https://www.fancode.com/live",
                        "https://www.fancode.com",
                    ):
                        continue

                # Clean lines to filter out empty / generic status lines
                lines = [line.strip() for line in text.split("\n") if line.strip()]

                candidate_title = ""
                tour_name = None

                # Priority 1: Look for a line with strong "vs" / "v" match pattern
                vs_index = -1
                for idx, line in enumerate(lines):
                    if is_vs_title(line) and is_valid_match_title(line):
                        candidate_title = line
                        vs_index = idx
                        break

                if candidate_title:
                    # Any preceding valid non-generic line is captured as the tour name
                    for prev_idx in range(vs_index):
                        prev_line = lines[prev_idx]
                        if is_valid_match_title(prev_line) and not is_vs_title(prev_line):
                            tour_name = prev_line
                            break
                else:
                    # Priority 2: Attempt title recovery from URL slug if available
                    if href:
                        recovered = extract_title_from_slug_or_url(href)
                        if recovered:
                            candidate_title = recovered
                            # The first non-generic text line may be the tour name
                            for line in lines:
                                if is_valid_match_title(line) and line.lower() != recovered.lower():
                                    tour_name = line
                                    break

                # Priority 3: Fallback to first non-generic line if nothing else recovered
                if not candidate_title:
                    for line in lines:
                        if is_valid_match_title(line):
                            candidate_title = line
                            break

                if not candidate_title or not is_valid_match_title(candidate_title):
                    continue

                # Extract match ID from href if present
                match_id = extract_match_id_from_url(href) if href else None

                card_data = {
                    "title": candidate_title,
                    "url": href,
                    "status": "LIVE",
                    "isLive": True,
                    "id": match_id,
                }
                if tour_name:
                    card_data["tour"] = {"name": tour_name}

                dom_items.append(RawLiveItem(raw_data=card_data, source_type="dom"))
        except Exception as exc:
            logger.debug("Error in DOM fallback extraction: %s", exc)
        return dom_items

    def _persist_to_database(self, records: List[LiveMatchRecord]) -> None:
        """Resolve live items against existing database records and enrich."""
        init_db()
        items_seen = len(records)
        items_updated = 0
        items_created = 0
        items_skipped = 0
        errors = 0

        with get_session() as session:
            runs_repo = ScrapeRunsRepository(session)
            run = runs_repo.create_run(
                run_type="live_now",
                metadata_json={"target_url": self.live_url, "max_items": self.max_items},
            )
            run_id = run.id

            matches_repo = MatchesRepository(session)
            sports_repo = SportsRepository(session)
            tours_repo = ToursRepository(session)

            for rec in records:
                try:
                    # Enforce strict title validation before any DB interaction
                    if not is_valid_match_title(rec.title):
                        items_skipped += 1
                        logger.warning(
                            "Invalid/generic live record skipped: title=%r, url=%r",
                            rec.title,
                            rec.source_url,
                        )
                        continue

                    # Match identity resolution (Priority: 1. external_id, 2. canonical source_url, 3. safe slug)
                    existing: Optional[Match] = None
                    clean_ext_id = clean_match_external_id(rec.match_external_id)

                    # 1. Primary Identity: external_id
                    if clean_ext_id:
                        existing = matches_repo.get_by_external_id(clean_ext_id)
                        if existing:
                            logger.info(
                                "Resolved Live Now match by external_id=%s -> match_id=%s (%s)",
                                clean_ext_id,
                                existing.id,
                                existing.title,
                            )
                        else:
                            logger.debug(
                                "Live Now external_id=%s not found in DB; attempting safe fallback",
                                clean_ext_id,
                            )

                    # 2. Fallback: Exact canonical specific source_url
                    if not existing and rec.source_url:
                        norm = normalize_url(rec.source_url) or rec.source_url
                        if norm not in (
                            "https://www.fancode.com",
                            "https://www.fancode.com/",
                            "https://www.fancode.com/live",
                            "https://www.fancode.com/live-now",
                            "https://www.fancode.com/live-now/all-sports",
                            "https://www.fancode.com/schedule",
                            "https://www.fancode.com/video",
                        ):
                            existing = matches_repo.get_by_source_url(rec.source_url)
                            if existing:
                                logger.info(
                                    "Resolved Live Now match by source_url -> match_id=%s (%s)",
                                    existing.id,
                                    existing.title,
                                )

                    # 3. Fallback: Safe slug (never generic ordinal slug)
                    if not existing and rec.title:
                        clean_slug = derive_slug(rec.title)
                        if (
                            clean_slug
                            and clean_slug not in ("match", "live", "unnamed-match", "game", "fixture", "final", "finals")
                            and not clean_slug.startswith("match-")
                        ):
                            existing = matches_repo.get_by_slug(clean_slug)
                            if existing:
                                logger.info(
                                    "Resolved Live Now match by slug=%s -> match_id=%s (%s)",
                                    clean_slug,
                                    existing.id,
                                    existing.title,
                                )

                    if existing:
                        # Non-destructive field enrichment
                        if not existing.external_id and clean_ext_id:
                            existing.external_id = clean_ext_id
                        if rec.status:
                            existing.status = rec.status
                        if rec.score_summary:
                            existing.score_summary = rec.score_summary
                        if not existing.venue and rec.venue:
                            existing.venue = rec.venue
                        if not existing.team_a_name and rec.team_a_name:
                            existing.team_a_name = rec.team_a_name
                        if not existing.team_b_name and rec.team_b_name:
                            existing.team_b_name = rec.team_b_name
                        if not existing.team_a_logo_url and rec.team_a_logo:
                            existing.team_a_logo_url = rec.team_a_logo
                        if not existing.team_b_logo_url and rec.team_b_logo:
                            existing.team_b_logo_url = rec.team_b_logo
                        if not existing.image_url and rec.thumbnail_url:
                            existing.image_url = rec.thumbnail_url

                        existing.last_seen_at = utc_now()
                        rec.match_id = existing.id
                        items_updated += 1
                        logger.info("Enriched existing live match [ID=%s]: %s", existing.id, existing.title)
                    else:
                        # Invariant 6: Create new Match only if sufficient identity exists (valid external_id, title, non-generic URL)
                        target_url = rec.source_url or (f"https://www.fancode.com/matches/{clean_ext_id}" if clean_ext_id else "")
                        if has_sufficient_match_identity(clean_ext_id, target_url, rec.title):
                            # Link sport/tour if present
                            sport_id = None
                            if rec.sport_name:
                                sp = sports_repo.upsert(
                                    name=rec.sport_name,
                                    slug=derive_slug(rec.sport_name),
                                    source_url=target_url,
                                )
                                sport_id = sp.id

                            tour_id = None
                            if rec.tour_name:
                                tr = tours_repo.upsert(
                                    name=rec.tour_name,
                                    slug=derive_slug(rec.tour_name),
                                    source_url=target_url,
                                    sport_id=sport_id,
                                    status="LIVE",
                                )
                                tour_id = tr.id

                            new_m = matches_repo.upsert(
                                external_id=clean_ext_id,
                                title=rec.title,
                                slug=derive_slug(rec.title, clean_ext_id),
                                source_url=target_url,
                                status=rec.status,
                                sport_id=sport_id,
                                tour_id=tour_id,
                                match_date=rec.match_date,
                                start_time=rec.start_time,
                                venue=rec.venue,
                                team_a_name=rec.team_a_name,
                                team_b_name=rec.team_b_name,
                                team_a_logo_url=rec.team_a_logo,
                                team_b_logo_url=rec.team_b_logo,
                                score_summary=rec.score_summary,
                                image_url=rec.thumbnail_url,
                            )
                            rec.match_id = new_m.id
                            items_created += 1
                            logger.info("Created new match from Live Now [ID=%s]: %s", new_m.id, new_m.title)
                        else:
                            items_skipped += 1
                            logger.warning(
                                "Unmatched live record skipped to prevent DB pollution: title=%r, url=%r, external_id=%r",
                                rec.title,
                                rec.source_url,
                                clean_ext_id,
                            )
                except Exception as exc:
                    errors += 1
                    logger.error("Error persisting live record %s: %s", rec.title, exc)

            runs_repo.finish_run(
                run_id=run_id,
                status="success" if errors == 0 else "partial",
                records_processed=items_seen,
                records_created=items_created,
                records_updated=items_updated,
                errors_count=errors,
            )

    def _save_raw_payloads(self, payloads: List[dict]) -> None:
        """Save raw payloads for offline debugging."""
        try:
            out_dir = Path(settings.LIVE_NOW_RAW_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_path = out_dir / f"live_payloads_{ts}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payloads, f, indent=2)
            logger.info("Saved raw Live Now payloads to %s", file_path)
        except Exception as exc:
            logger.warning("Failed saving raw payloads: %s", exc)
