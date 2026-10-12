"""
Media Reporting System - Exchange4media Articles Endpoint (Phase 3)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.dashboard import E4MArticlesResponse
from app.services.exchange4media_service import (
    load_exchange4media_data,
    run_exchange4media_refresh,
)

router = APIRouter(prefix="/monitoring/exchange4media", tags=["Exchange4media Monitoring"])


@router.get("/articles", response_model=E4MArticlesResponse)
async def get_exchange4media_articles(
    section: Optional[str] = Query(None, description="Filter articles by editorial section"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of articles to return"),
    skip: int = Query(0, ge=0, description="Number of articles to skip"),
):
    """
    Returns verified real articles from Exchange4media extracted during Phase 3 scraping.
    Source of truth: scraper_output/exchange4media.json
    """
    data = load_exchange4media_data()

    articles = data["articles"]
    if section and section.lower() != "all":
        articles = [
            a for a in articles
            if a.get("section", "").lower() == section.lower()
        ]

    paginated = articles[skip : skip + limit]

    return {
        "website": data["website"],
        "generated_at": data["generated_at"],
        "count": len(articles),
        "sections": data["sections"],
        "articles": paginated,
        "stats": data["stats"],
        "source_file": data.get("source_file"),
        "is_available": data.get("is_available", False),
    }


@router.post("/refresh", response_model=E4MArticlesResponse)
def refresh_exchange4media_articles():
    """
    Triggers a live scrape refresh of Exchange4media, updates scraper_output/exchange4media.json,
    and returns the updated articles.
    """
    data = run_exchange4media_refresh()
    return {
        "website": data["website"],
        "generated_at": data["generated_at"],
        "count": data["count"],
        "sections": data["sections"],
        "articles": data["articles"],
        "stats": data["stats"],
        "source_file": data.get("source_file"),
        "is_available": data.get("is_available", False),
    }

