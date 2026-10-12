"""
Media Reporting System - ET BrandEquity Scraper Data Service
Loads, validates, and normalizes real scraper output from scraper_output/et_brand_equity.json.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("et-service")


def find_scraper_output_file() -> Path:
    """
    Locates scraper_output/et_brand_equity.json across standard runtime directory structures.
    """
    env_path = os.getenv("ET_SCRAPER_OUTPUT_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    # 1. Look from backend/app/services -> media-reporting-system/scraper_output/et_brand_equity.json
    service_dir = Path(__file__).resolve().parent
    candidates = [
        service_dir.parents[2] / "scraper_output" / "et_brand_equity.json",
        Path.cwd() / "scraper_output" / "et_brand_equity.json",
        Path.cwd().parent / "scraper_output" / "et_brand_equity.json",
        Path("d:/MFA/media-reporting-system/scraper_output/et_brand_equity.json"),
        Path("scraper_output/et_brand_equity.json"),
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    # Default expected path even if missing
    return candidates[0]


def extract_article_id_from_url(url: str, fallback_hash: str = "") -> str:
    """Derives a stable, clean article identifier from the ET BrandEquity URL or content hash."""
    if url:
        match = re.search(r"/(\d{7,10})(?:/|\.cms)?$", url)
        if match:
            return f"et-{match.group(1)}"
    if fallback_hash:
        return f"et-{fallback_hash[:12]}"
    return f"et-{abs(hash(url))}"


def load_et_brand_equity_data() -> Dict[str, Any]:
    """
    Loads and normalizes the verified Phase 2A ET BrandEquity scraper output.
    Returns a structured dictionary containing website metadata, quality statistics,
    and normalized article models.
    """
    file_path = find_scraper_output_file()

    default_result: Dict[str, Any] = {
        "website": {
            "key": "et_brand_equity",
            "name": "ET BrandEquity",
            "url": "https://brandequity.economictimes.indiatimes.com/",
            "status": "DATA UNAVAILABLE",
        },
        "generated_at": None,
        "count": 0,
        "sections": [],
        "articles": [],
        "stats": {
            "articles_today": 0,
            "articles_with_image": 0,
            "articles_with_summary": 0,
            "articles_with_published_at": 0,
            "latest_scraped_at": None,
        },
        "source_file": str(file_path.name),
        "is_available": False,
    }

    data = {}
    try:
        if file_path.exists():
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    except (OSError, ValueError) as exc:
        logger.warning("Snapshot unavailable; checking database: %s", exc)
    raw_articles = data.get("articles", [])
    if not isinstance(raw_articles, list):
        raw_articles = []

    normalized_articles: List[Dict[str, Any]] = []
    sections_set = set()
    articles_with_image = 0
    articles_with_summary = 0
    articles_with_published_at = 0
    articles_today = 0
    latest_scraped_at = None

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for art in raw_articles:
        if not isinstance(art, dict):
            continue

        headline = str(art.get("headline") or "").strip()
        url = str(art.get("url") or "").strip()
        if not headline or not url:
            continue

        section = str(art.get("section") or "Overall").strip()
        sections_set.add(section)

        image_url = art.get("image_url") or None
        if image_url:
            articles_with_image += 1

        summary = art.get("summary") or None
        is_exclusive = bool(art.get("is_exclusive"))
        publication_label = art.get("publication_label") or None

        # Clean legacy summary if it contains concatenated Exclusive tag or relative time
        if summary:
            if summary.strip().endswith(" Exclusive") or summary.strip().endswith(" [Exclusive]") or summary.strip() == "Exclusive":
                cleaned_sum = re.sub(r"\s*\[?Exclusive\]?\s*$", "", summary, flags=re.IGNORECASE).strip()
                if cleaned_sum == headline or not cleaned_sum:
                    summary = None
                else:
                    summary = cleaned_sum
                is_exclusive = True
            elif re.search(r"\s+(\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago|just now)\s*$", summary, re.I):
                m_rel = re.search(r"(\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago|just now)\s*$", summary, re.I)
                if not publication_label and m_rel:
                    publication_label = m_rel.group(1).strip()
                cleaned_sum = re.sub(r"\s+(\d+\s*(?:mins?|minutes?|hrs?|hours?|days?)\s*ago|just now)\s*$", "", summary, flags=re.I).strip()
                if cleaned_sum == headline or not cleaned_sum:
                    summary = None
                else:
                    summary = cleaned_sum

        if summary:
            articles_with_summary += 1

        published_at = art.get("published_at") or None
        if published_at:
            articles_with_published_at += 1
            if str(published_at).startswith(today_str):
                articles_today += 1

        scraped_at = art.get("scraped_at") or ""
        if scraped_at and (not latest_scraped_at or scraped_at > latest_scraped_at):
            latest_scraped_at = scraped_at

        content_hash = art.get("content_hash") or ""
        article_id = extract_article_id_from_url(url, content_hash)

        normalized_article = {
            "id": article_id,
            "headline": headline,
            "url": url,
            "image_url": image_url,
            "summary": summary,
            "section": section,
            "published_at": published_at,
            "publication_label": publication_label,
            "is_exclusive": is_exclusive,
            "scraped_at": scraped_at,
            "content_hash": content_hash,
            "website": "ET BrandEquity",
            "website_key": "et_brand_equity",
            "status": "CURRENT",
            "read_time": "3 min read",
        }
        normalized_articles.append(normalized_article)

    # Sort articles: newest published_at first, fallback to scraped_at
    def sort_key(a: Dict[str, Any]) -> str:
        return a.get("published_at") or a.get("scraped_at") or ""

    normalized_articles.sort(key=sort_key, reverse=True)

    generated_at = data.get("generated_at") or latest_scraped_at

    # Read the complete published archive, including stories rotated off listings.
    try:
        from database.repository import db_repo
        db_arts = db_repo.get_articles(website_key="et_brand_equity", status="all", limit=None)
        if db_arts:
            db_sections = sorted(list({a.get("section_name") or "Overall" for a in db_arts}))
            db_normalized = []
            db_with_image = 0
            db_with_summary = 0
            db_with_pub = 0
            db_today = 0
            db_latest_scraped = None

            for a in db_arts:
                art_id = extract_article_id_from_url(a["url"], a["content_hash"])
                if a.get("image_url"):
                    db_with_image += 1
                if a.get("summary"):
                    db_with_summary += 1
                if a.get("published_at"):
                    db_with_pub += 1
                    if str(a["published_at"]).startswith(today_str):
                        db_today += 1
                seen = a.get("last_seen_at") or a.get("first_seen_at")
                if seen and (not db_latest_scraped or seen > db_latest_scraped):
                    db_latest_scraped = seen

                db_normalized.append({
                    "id": art_id,
                    "headline": a["headline"],
                    "url": a["url"],
                    "image_url": a.get("image_url"),
                    "summary": a.get("summary"),
                    "section": a.get("section_name") or "Overall",
                    "published_at": a.get("published_at"),
                    "publication_label": a.get("publication_label"),
                    "is_exclusive": bool(a.get("is_exclusive")),
                    "scraped_at": a.get("first_seen_at") or a.get("created_at"),
                    "first_seen_at": a.get("first_seen_at") or a.get("created_at"),
                    "last_seen_at": a.get("last_seen_at"),
                    "content_hash": a["content_hash"],
                    "website": "ET BrandEquity",
                    "website_key": "et_brand_equity",
                    "status": "CURRENT",
                    "read_time": "3 min read",
                })
            db_normalized.sort(key=sort_key, reverse=True)

            return {
                "website": {
                    "key": "et_brand_equity",
                    "name": "ET BrandEquity",
                    "url": "https://brandequity.economictimes.indiatimes.com/",
                    "status": "AVAILABLE",
                },
                "generated_at": db_latest_scraped,
                "count": len(db_normalized),
                "sections": db_sections,
                "articles": db_normalized,
                "stats": {
                    "articles_today": db_today,
                    "articles_with_image": db_with_image,
                    "articles_with_summary": db_with_summary,
                    "articles_with_published_at": db_with_pub,
                    "latest_scraped_at": db_latest_scraped,
                },
                "source_file": "database:articles",
                "is_available": True,
            }
    except Exception as exc:
        logger.debug("Database load fallback to file for ET BrandEquity: %s", exc)

    return {
        "website": {
            "key": "et_brand_equity",
            "name": "ET BrandEquity",
            "url": "https://brandequity.economictimes.indiatimes.com/",
            "status": "AVAILABLE" if normalized_articles else "DATA UNAVAILABLE",
        },
        "generated_at": generated_at,
        "count": len(normalized_articles),
        "sections": sorted(list(sections_set)),
        "articles": normalized_articles,
        "stats": {
            "articles_today": articles_today,
            "articles_with_image": articles_with_image,
            "articles_with_summary": articles_with_summary,
            "articles_with_published_at": articles_with_published_at,
            "latest_scraped_at": latest_scraped_at,
        },
        "source_file": str(file_path.name),
        "is_available": len(normalized_articles) > 0,
    }


def load_et_brand_equity_articles() -> List[Dict[str, Any]]:
    """Convenience helper returning just the list of normalized ET BrandEquity articles."""
    return load_et_brand_equity_data()["articles"]


def run_et_brand_equity_refresh() -> Dict[str, Any]:
    """
    Executes a fresh crawl of ET BrandEquity, updates database & scraper_output,
    and returns normalized live articles.
    """
    from monitoring.engine import run_website_refresh
    from fastapi import HTTPException
    ok, _, error = run_website_refresh("et_brand_equity", "ET BrandEquity")
    if not ok:
        raise HTTPException(status_code=502, detail=error)
    return load_et_brand_equity_data()
