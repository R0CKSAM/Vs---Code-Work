"""
Media Reporting System - Phase 5 Monitoring Engine
Automatically scrapes ET BrandEquity, Exchange4media, Campaign India,
BestMediaInfo, Social Samosa, Adgully, and MediaBrief every N minutes,
persists results through the Phase 4 change detection layer, and updates
in-memory monitoring status for the dashboard.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("monitor")

# ── Configuration ──────────────────────────────────────────────────────────

def get_interval_minutes() -> int:
    """Returns configured interval from env, defaulting to 10 minutes."""
    try:
        return max(1, int(os.getenv("MONITORING_INTERVAL_MINUTES", "10")))
    except (ValueError, TypeError):
        return 10


# ── Website registry ───────────────────────────────────────────────────────

MONITORED_WEBSITES: List[Dict] = [
    {
        "key": "et_brand_equity",
        "name": "ET BrandEquity",
        "url": "https://brandequity.economictimes.indiatimes.com/",
    },
    {
        "key": "exchange4media",
        "name": "Exchange4media",
        "url": "https://www.exchange4media.com/",
    },
    {
        "key": "campaign_india",
        "name": "Campaign India",
        "url": "https://www.campaignindia.in/news",
    },
    {
        "key": "bestmediainfo",
        "name": "BestMediaInfo",
        "url": "https://bestmediainfo.com/",
    },
    {
        "key": "social_samosa",
        "name": "Social Samosa",
        "url": "https://www.socialsamosa.com/",
    },
    {
        "key": "adgully",
        "name": "Adgully",
        "url": "https://www.adgully.com/",
    },
    {
        "key": "mediabrief",
        "name": "MediaBrief",
        "url": "https://mediabrief.com/",
    },
    {
        "key": "storyboard18",
        "name": "Storyboard18",
        "url": "https://www.storyboard18.com/",
    },
    {
        "key": "indiantelevision",
        "name": "Indian Television",
        "url": "https://indiantelevision.com/",
    },
]

# Every configured listing page is crawled without an article cap. Article URLs
# are persisted immediately; a publisher must not be hit with thousands of
# detail requests in one burst merely to complete optional metadata.
SCRAPER_REQUEST_DELAY_SECONDS = 0.5


# ── Scraper dispatch ───────────────────────────────────────────────────────

def _scrape_website(website_key: str) -> Tuple[List[Dict], bool, str]:
    """
    Runs the real scraper for the given website_key.
    Returns (dict_articles, success, error_message).
    Never raises — all exceptions are caught and returned as failure.
    """
    try:
        if website_key == "et_brand_equity":
            from scraper.et_brand_equity.scraper import ETBrandEquityScraper
            scraper = ETBrandEquityScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "exchange4media":
            from scraper.exchange4media.scraper import Exchange4mediaScraper
            scraper = Exchange4mediaScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "campaign_india":
            from scraper.campaign_india.scraper import CampaignIndiaScraper
            scraper = CampaignIndiaScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "bestmediainfo":
            from scraper.bestmediainfo.scraper import BestMediaInfoScraper
            scraper = BestMediaInfoScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "social_samosa":
            from scraper.social_samosa.scraper import SocialSamosaScraper
            scraper = SocialSamosaScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "adgully":
            from scraper.adgully.scraper import AdgullyScraper
            scraper = AdgullyScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "mediabrief":
            from scraper.mediabrief.scraper import MediaBriefScraper
            scraper = MediaBriefScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "storyboard18":
            from scraper.storyboard18.scraper import Storyboard18Scraper
            scraper = Storyboard18Scraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        elif website_key == "indiantelevision":
            from scraper.indiantelevision.scraper import IndianTelevisionScraper
            scraper = IndianTelevisionScraper(delay_seconds=SCRAPER_REQUEST_DELAY_SECONDS)
        else:
            return [], False, f"Unknown website key: {website_key}"

        # Discovery is exhaustive across homepage + configured section pages.
        articles_raw, _stats = scraper.scrape_homepage(enrich=False, max_enrich=None)

        if not articles_raw:
            return [], False, "Scraper returned 0 articles"

        # Convert Article dataclass objects → plain dicts
        dict_articles = []
        for a in articles_raw:
            if hasattr(a, "to_dict"):
                dict_articles.append(a.to_dict())
            elif dataclasses.is_dataclass(a):
                dict_articles.append(dataclasses.asdict(a))
            else:
                dict_articles.append(dict(a))

        return dict_articles, True, ""

    except Exception as exc:
        return [], False, str(exc)


def _validate_articles(
    website_key: str, articles: List[Dict], min_count: int = 5
) -> Tuple[bool, str]:
    """
    Safety validation before passing articles to Phase 4 change detection.
    Returns (valid, reason).
    """
    if not isinstance(articles, list):
        return False, "Article result is not a list"
    if len(articles) < min_count:
        return False, f"Too few articles ({len(articles)}) — below safety threshold {min_count}"
    # Spot-check a few articles have expected website_key and URL
    for art in articles[:5]:
        if not isinstance(art, dict):
            return False, "Article entry is not a dict"
        if not art.get("url"):
            return False, "Article missing canonical URL"
        art_key = art.get("website_key", "")
        if art_key and art_key != website_key:
            return False, f"Cross-website contamination: expected {website_key}, got {art_key}"
    return True, ""


# ── Per-website refresh ────────────────────────────────────────────────────

_refresh_locks = {site["key"]: threading.Lock() for site in MONITORED_WEBSITES}


def run_website_refresh(website_key: str, website_name: str) -> Tuple[bool, int, str]:
    lock = _refresh_locks.get(website_key)
    if lock is None:
        return False, 0, f"Unknown website key: {website_key}"
    with lock:
        return _run_website_refresh(website_key, website_name)


def _run_website_refresh(website_key: str, website_name: str) -> Tuple[bool, int, str]:
    """
    Full refresh pipeline for one website:
      1. Scrape
      2. Validate
      3. Phase 4 change detection + persistence
      4. Return (success, article_count, error_message)
    """
    logger.info("[MONITOR] %s refresh started", website_name)

    # Step 1: Scrape
    dict_articles, scrape_ok, scrape_error = _scrape_website(website_key)
    if not scrape_ok:
        logger.warning("[MONITOR] %s refresh FAILED: %s", website_name, scrape_error)
        return False, 0, scrape_error

    # Step 2: Validate
    valid, reason = _validate_articles(website_key, dict_articles)
    if not valid:
        msg = f"Validation failed: {reason}"
        logger.warning("[MONITOR] %s %s", website_name, msg)
        return False, 0, msg

    # Step 3: Phase 4 change detection
    try:
        from app.services.change_detector import change_detector
        result = change_detector.process_scraped_articles(
            website_key,
            dict_articles,
            scrape_success=True,
        )
        article_count = len(dict_articles)
        logger.info(
            "[MONITOR] %s refresh completed: %d articles "
            "(new=%d updated=%d unchanged=%d removed=%d)",
            website_name,
            article_count,
            result.get("new", 0),
            result.get("updated", 0),
            result.get("unchanged", 0),
            result.get("removed", 0),
        )

        # Step 3b: Backfill missing publication timestamps for existing active articles
        try:
            from database.repository import db_repo
            from scraper.base.fetcher import PageFetcher
            from scraper.base.enrichment import enrich_article_dict
            import json

            # Backfill at most 10 missing timestamps per cycle so refresh remains snappy
            missing_pub_arts = db_repo.get_articles_missing_published_at(website_key=website_key, limit=10)
            if missing_pub_arts:
                bf_fetcher = PageFetcher()
                backfilled_count = 0
                for m_art in missing_pub_arts:
                    enriched = enrich_article_dict(m_art, bf_fetcher)
                    p_at = enriched.get("published_at")
                    if p_at:
                        db_repo.update_article_published_at(m_art["id"], p_at)
                        backfilled_count += 1
                if backfilled_count > 0:
                    logger.info(
                        "[MONITOR] %s publication time backfill: updated %d/%d articles",
                        website_name,
                        backfilled_count,
                        len(missing_pub_arts),
                    )
                    try:
                        from app.services.generic_source_service import find_source_scraper_output_file
                        out_file = find_source_scraper_output_file(website_key)
                        db_articles = db_repo.get_articles(website_key=website_key, status="all", limit=None)
                        if db_articles:
                            payload = {
                                "generated_at": datetime.now(timezone.utc).isoformat(),
                                "website": website_key,
                                "articles": db_articles,
                                "count": len(db_articles),
                            }
                            out_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(out_file, "w", encoding="utf-8") as f:
                                json.dump(payload, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
        except Exception as bf_exc:
            logger.warning("[MONITOR] %s publication time backfill notice: %s", website_name, bf_exc)

        # Step 4: Phase 6 Advertisement Detection & Persistence
        try:
            from scraper.advertisements import AdvertisementDetector
            from app.services.ad_change_detector import ad_change_detector
            from scraper.base.fetcher import PageFetcher

            site_entry = next((s for s in MONITORED_WEBSITES if s["key"] == website_key), None)
            base_url = site_entry["url"] if site_entry else "https://www.exchange4media.com/"

            from scraper.ad_collection import collect_advertisements
            detected_ads = collect_advertisements(website_key, base_url)
            if detected_ads:
                ad_res = ad_change_detector.process_detected_advertisements(
                    website_key=website_key,
                    detected_ads=detected_ads,
                    scrape_success=True,
                    download_images=True,
                    allow_removals=False,
                )
                logger.info(
                    "[MONITOR] %s ad monitoring: %d detected (new=%d changed=%d unchanged=%d removed=%d)",
                    website_name,
                    ad_res.get("detected_count", 0),
                    ad_res.get("new", 0),
                    ad_res.get("changed", 0),
                    ad_res.get("unchanged", 0),
                    ad_res.get("removed", 0),
                )
        except Exception as ad_exc:
            logger.warning("[MONITOR] %s advertisement monitoring notice: %s", website_name, ad_exc)

        return True, article_count, ""
    except Exception as exc:
        msg = f"Persistence error: {exc}"
        logger.error("[MONITOR] %s %s", website_name, msg)
        return False, 0, msg


# ── Full monitoring cycle ──────────────────────────────────────────────────

def run_monitoring_cycle() -> str:
    """
    Executes one full monitoring cycle across all configured websites.
    Each website runs independently — one failure does not cancel others.
    Returns cycle status: SUCCESS | PARTIAL_SUCCESS | FAILED
    """
    from monitoring.status import monitoring_status

    if monitoring_status.is_running():
        logger.info("[MONITOR] Cycle already running — skipping duplicate trigger")
        return "ALREADY_RUNNING"

    monitoring_status.mark_cycle_started()
    logger.info("[MONITOR] Cycle started (%d websites)", len(MONITORED_WEBSITES))

    successes = 0
    failures = 0

    for site in MONITORED_WEBSITES:
        key = site["key"]
        name = site["name"]

        monitoring_status.mark_website_attempt(key)
        try:
            ok, count, err = run_website_refresh(key, name)
            if ok:
                monitoring_status.mark_website_success(key, count)
                successes += 1
            else:
                monitoring_status.mark_website_failed(key, err)
                failures += 1
        except Exception as exc:
            err_msg = str(exc)
            logger.exception("[MONITOR] Unexpected error for %s: %s", name, err_msg)
            monitoring_status.mark_website_failed(key, err_msg)
            failures += 1

    # Determine cycle status
    if failures == 0:
        cycle_status = "SUCCESS"
    elif successes == 0:
        cycle_status = "FAILED"
    else:
        cycle_status = "PARTIAL_SUCCESS"

    monitoring_status.mark_cycle_completed(cycle_status)
    logger.info("[MONITOR] Cycle completed: %s (ok=%d fail=%d)", cycle_status, successes, failures)
    return cycle_status
