"""
Media Reporting System - Generic Source Data Service
Loads, normalizes, and refreshes articles for registered media publishers.
Prioritizes database records and falls back to snapshot files in scraper_output/.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("source-service")


def find_source_scraper_output_file(website_key: str) -> Path:
    env_var_name = f"{website_key.upper()}_SCRAPER_OUTPUT_PATH"
    env_path = os.getenv(env_var_name)
    if env_path and Path(env_path).exists():
        return Path(env_path)

    service_dir = Path(__file__).resolve().parent
    filename = f"{website_key}.json"
    candidates = [
        service_dir.parents[2] / "scraper_output" / filename,
        Path.cwd() / "scraper_output" / filename,
        Path.cwd().parent / "scraper_output" / filename,
        Path(f"d:/MFA/media-reporting-system/scraper_output/{filename}"),
        Path(f"scraper_output/{filename}"),
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return candidates[0]


def extract_source_article_id(website_key: str, url: str, fallback_hash: str = "") -> str:
    prefix = website_key[:4]
    if url:
        match = re.search(r"[-/](\d{4,10})(?:/|\.html|\.cms)?$", url)
        if match:
            return f"{prefix}-{match.group(1)}"
        slug = url.strip("/").split("/")[-1].replace(".html", "")
        if slug and len(slug) >= 5:
            return f"{prefix}-{slug[:30]}"
    if fallback_hash:
        return f"{prefix}-{fallback_hash[:12]}"
    return f"{prefix}-{abs(hash(url))}"


def load_source_data(website_key: str, website_name: str, base_url: str) -> Dict[str, Any]:
    """
    Loads and normalizes real articles for any registered website.
    Checks the database first as the primary source of truth, then falls back
    to scraper_output/<website_key>.json.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Check database first
    try:
        from database.repository import db_repo
        db_arts = db_repo.get_articles(website_key=website_key, status="active", limit=150)
        if db_arts:
            db_sections = sorted(list({a.get("section_name") or "Overall" for a in db_arts}))
            db_normalized = []
            db_with_image = 0
            db_with_summary = 0
            db_with_pub = 0
            db_today = 0
            db_latest_scraped = None

            for a in db_arts:
                art_id = extract_source_article_id(website_key, a["url"], a["content_hash"])
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
                    "scraped_at": a.get("last_seen_at") or a.get("first_seen_at"),
                    "content_hash": a["content_hash"],
                    "website": website_name,
                    "website_key": website_key,
                    "status": "CURRENT",
                    "read_time": "3 min read",
                })

            def sort_key(item: Dict[str, Any]) -> str:
                return item.get("published_at") or item.get("scraped_at") or ""

            db_normalized.sort(key=sort_key, reverse=True)

            return {
                "website": {
                    "key": website_key,
                    "name": website_name,
                    "url": base_url,
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
        logger.debug("Database load fallback to snapshot file for %s: %s", website_key, exc)

    # 2. Fallback to snapshot file in scraper_output
    file_path = find_source_scraper_output_file(website_key)
    raw_articles: List[Dict[str, Any]] = []
    generated_at = None

    if file_path.exists():
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_articles = loaded.get("articles", [])
                generated_at = loaded.get("generated_at")
            elif isinstance(loaded, list):
                raw_articles = loaded
        except Exception as exc:
            logger.warning("Error reading snapshot file %s: %s", file_path, exc)

    normalized_articles: List[Dict[str, Any]] = []
    sections_set = set()
    articles_with_image = 0
    articles_with_summary = 0
    articles_with_published_at = 0
    articles_today = 0
    latest_scraped_at = None

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
        art_id = extract_source_article_id(website_key, url, content_hash)

        normalized_articles.append({
            "id": art_id,
            "headline": headline,
            "url": url,
            "image_url": image_url,
            "summary": summary,
            "section": section,
            "published_at": published_at,
            "publication_label": art.get("publication_label"),
            "is_exclusive": bool(art.get("is_exclusive")),
            "scraped_at": scraped_at,
            "content_hash": content_hash,
            "website": website_name,
            "website_key": website_key,
            "status": "CURRENT",
            "read_time": "3 min read",
        })

    def sort_key(item: Dict[str, Any]) -> str:
        return item.get("published_at") or item.get("scraped_at") or ""

    normalized_articles.sort(key=sort_key, reverse=True)

    return {
        "website": {
            "key": website_key,
            "name": website_name,
            "url": base_url,
            "status": "AVAILABLE" if normalized_articles else "DATA UNAVAILABLE",
        },
        "generated_at": generated_at or latest_scraped_at,
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


def run_source_refresh(website_key: str, website_name: str, base_url: str) -> Dict[str, Any]:
    from monitoring.engine import run_website_refresh
    from fastapi import HTTPException
    ok, _, error = run_website_refresh(website_key, website_name)
    if not ok:
        raise HTTPException(status_code=502, detail=error or f"Failed refreshing {website_name}")
    return load_source_data(website_key, website_name, base_url)
