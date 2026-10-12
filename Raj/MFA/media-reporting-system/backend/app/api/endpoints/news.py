"""
Unified news search endpoint for the dashboard News Search screen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database.repository import db_repo

router = APIRouter(prefix="/news", tags=["News Search"])

WEBSITE_ALIASES = {
    "et": "et_brand_equity",
    "et-brand-equity": "et_brand_equity",
    "et_brand_equity": "et_brand_equity",
    "e4m": "exchange4media",
    "exchange4media": "exchange4media",
    "campaign-india": "campaign_india",
    "campaign_india": "campaign_india",
    "bestmediainfo": "bestmediainfo",
    "social-samosa": "social_samosa",
    "social_samosa": "social_samosa",
    "adgully": "adgully",
    "mediabrief": "mediabrief",
    "storyboard18": "storyboard18",
    "storyboard-18": "storyboard18",
    "sb18": "storyboard18",
    "indiantelevision": "indiantelevision",
    "indian-television": "indiantelevision",
    "itv": "indiantelevision",
}


def _date_or_none(value: Optional[str], field_name: str) -> Optional[str]:
    if not value:
        return None
    clean = value.strip()
    try:
        datetime.strptime(clean, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field_name} must be YYYY-MM-DD.")
    return clean


def _article_payload(row):
    return {
        "id": row["id"],
        "headline": row.get("headline"),
        "summary": row.get("summary"),
        "source": row.get("website_name"),
        "website_key": row.get("website_key"),
        "section": row.get("section_name") or "General",
        "published_at": row.get("published_at"),
        "scraped_at": row.get("first_seen_at") or row.get("created_at"),
        "first_seen_at": row.get("first_seen_at") or row.get("created_at"),
        "publication_label": row.get("publication_label"),
        "is_exclusive": bool(row.get("is_exclusive")),
        "image_url": row.get("image_url"),
        "url": row.get("url"),
        "status": row.get("status") or "CURRENT",
    }


@router.get("/search")
async def search_news(
    q: Optional[str] = Query(None, description="Keyword search across headline, summary, section, source, URL"),
    source: Optional[str] = Query(None, description="Website key or UI alias"),
    section: Optional[str] = Query(None, description="Section name"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    page: int = Query(1, ge=1),
):
    website_key = None
    if source and source.lower() != "all":
        website_key = WEBSITE_ALIASES.get(source.strip().lower(), source.strip())

    start = _date_or_none(start_date, "start_date")
    end = _date_or_none(end_date, "end_date")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date.")

    skip = (page - 1) * limit
    result = db_repo.search_articles(
        search=(q or "").strip() or None,
        website_key=website_key,
        section_name=section,
        start_date=start,
        end_date=end,
        # A publisher listing is transient. Include previously detected stories
        # even after they rotate off that listing and receive REMOVED status.
        status="all",
        limit=limit,
        skip=skip,
    )

    if result["total"] == 0 and db_repo.count_articles(status="all") == 0:
        try:
            from backend.app.services.generic_source_service import generic_source_service, REGISTERED_SOURCES
            sources_to_check = [website_key] if website_key else list(REGISTERED_SOURCES.keys())
            fallback_articles = []
            query_term = (q or "").strip().lower()
            for src_key in sources_to_check:
                bundle = generic_source_service.get_source_bundle(src_key)
                for art in bundle.get("articles", []):
                    if query_term:
                        text_corpus = f"{art.get('headline', '')} {art.get('summary', '')} {art.get('section', '')} {art.get('website', '')}".lower()
                        if query_term not in text_corpus:
                            continue
                    if section and section.lower() != "all":
                        if (art.get("section") or "").lower() != section.lower():
                            continue
                    fallback_articles.append({
                        "id": art.get("id"),
                        "headline": art.get("headline"),
                        "summary": art.get("summary"),
                        "source": art.get("website"),
                        "website_key": art.get("website_key") or src_key,
                        "section": art.get("section") or "General",
                        "published_at": art.get("published_at"),
                        "scraped_at": art.get("scraped_at"),
                        "publication_label": art.get("publication_label"),
                        "is_exclusive": bool(art.get("is_exclusive")),
                        "image_url": art.get("image_url"),
                        "url": art.get("url"),
                    })
            return {
                "query": q or "",
                "page": page,
                "limit": limit,
                "total": len(fallback_articles),
                "articles": fallback_articles[skip:skip + limit],
            }
        except Exception:
            pass

    return {
        "query": q or "",
        "page": page,
        "limit": limit,
        "total": result["total"],
        "articles": [_article_payload(row) for row in result["articles"]],
    }
