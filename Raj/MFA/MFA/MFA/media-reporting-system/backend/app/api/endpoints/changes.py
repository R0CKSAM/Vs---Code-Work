"""
Media Reporting System - Changes & Article History Endpoints (Phase 4)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.schemas.dashboard import (
    ArticleHistoryResponse,
    ArticleVersionItem,
    ChangeKPIsResponse,
    ChangesResponse,
)
from database.repository import db_repo

router = APIRouter(prefix="/monitoring", tags=["Change Detection & History"])


@router.get("/changes", response_model=ChangesResponse)
async def get_all_changes(
    website: Optional[str] = Query(None, description="Filter by website key (e.g., et_brand_equity, exchange4media)"),
    timeframe: str = Query("all", description="Timeframe filter: 'today', '24h', '7d', 'all'"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """
    Returns recent article modifications across all monitored websites or filtered by website.
    Includes NEW, UPDATED, and REMOVED change classifications.
    """
    website_key = None if website in (None, "all", "") else website
    raw_changes = db_repo.get_recent_changes(
        website_key=website_key,
        timeframe=timeframe,
        limit=limit,
        skip=skip,
    )
    kpis = db_repo.get_change_kpis(website_key=website_key, timeframe=timeframe)

    formatted_changes = []
    for c in raw_changes:
        formatted_changes.append({
            "version_id": c["version_id"],
            "article_id": c["article_id"],
            "headline": c["headline"],
            "url": c["url"],
            "image_url": c.get("image_url"),
            "summary": c.get("summary"),
            "section": c.get("section_name") or "Overall",
            "website_name": c["website_name"],
            "website_key": c["website_key"],
            "change_type": c["change_type"],
            "detected_at": c["detected_at"],
            "current_status": c["current_status"],
            "current_hash": c["current_hash"],
        })

    return {
        "timeframe": timeframe,
        "count": len(formatted_changes),
        "kpis": kpis,
        "changes": formatted_changes,
    }


@router.get("/{website}/changes", response_model=ChangesResponse)
async def get_website_changes(
    website: str,
    timeframe: str = Query("all", description="Timeframe filter: 'today', '24h', '7d', 'all'"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """
    Returns recent article modifications for a specific website.
    """
    return await get_all_changes(website=website, timeframe=timeframe, limit=limit, skip=skip)


@router.get("/{website}/articles/{article_id}/history", response_model=ArticleHistoryResponse)
async def get_article_history(
    website: str,
    article_id: str,
    url: Optional[str] = Query(None, description="Optional canonical article URL for direct lookup"),
):
    """
    Returns the complete chronological version history for an article.
    Accepts integer ID, formatted frontend ID (e.g. et-134424838), or ?url= parameter.
    """
    article = None
    if url:
        site_record = db_repo.get_website_by_key(website)
        if site_record:
            article = db_repo.get_article_by_url(site_record["id"], url)

    if not article and article_id.isdigit():
        article = db_repo.get_article_by_id(int(article_id))

    if not article:
        clean_id = article_id.replace("et-", "").replace("e4m-", "").strip()
        if clean_id:
            from database.connection import get_db
            with get_db(db_repo.db_path) as conn:
                row = conn.execute(
                    "SELECT * FROM articles WHERE url LIKE ? LIMIT 1",
                    (f"%{clean_id}%",),
                ).fetchone()
                if row:
                    article = dict(row)

    if not article:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")

    versions = db_repo.get_article_history(article["id"])
    formatted_versions = []
    for v in versions:
        formatted_versions.append(
            ArticleVersionItem(
                id=v["id"],
                article_id=v["article_id"],
                headline=v["headline"],
                url=v["url"],
                image_url=v.get("image_url"),
                summary=v.get("summary"),
                section_name=v.get("section_name"),
                published_at=v.get("published_at"),
                content_hash=v["content_hash"],
                detected_at=v["detected_at"],
                change_type=v["change_type"],
            )
        )


    return ArticleHistoryResponse(
        article_id=article["id"],
        headline=article["headline"],
        url=article["url"],
        status=article["status"],
        first_seen_at=article["first_seen_at"],
        last_seen_at=article["last_seen_at"],
        last_changed_at=article["last_changed_at"],
        versions_count=len(formatted_versions),
        versions=formatted_versions,
    )
