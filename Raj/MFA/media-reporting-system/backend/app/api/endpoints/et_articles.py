"""
Media Reporting System - ET BrandEquity Articles Endpoint (Phase 2B)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.dashboard import ETArticlesResponse
from app.services.et_brand_equity_service import (
    load_et_brand_equity_data,
    run_et_brand_equity_refresh,
)

router = APIRouter(prefix="/monitoring/et-brand-equity", tags=["ET BrandEquity Monitoring"])


@router.get("/articles", response_model=ETArticlesResponse)
async def get_et_brand_equity_articles(
    section: Optional[str] = Query(None, description="Filter articles by editorial section"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum articles; omitted returns all"),
    skip: int = Query(0, ge=0, description="Number of articles to skip"),
):
    """
    Returns verified real articles from ET BrandEquity extracted during Phase 2A scraping.
    Source of truth: scraper_output/et_brand_equity.json
    """
    data = load_et_brand_equity_data()
    articles = data.get("articles", [])
    if section and section.lower() != "all":
        articles = [
            a for a in articles
            if a.get("section", "").lower() == section.lower()
        ]

    paginated = articles[skip:] if limit is None else articles[skip : skip + limit]

    return {
        "website": data["website"],
        "generated_at": data["generated_at"],
        "count": len(articles),
        "sections": data.get("sections", []),
        "articles": paginated,
        "stats": data.get("stats"),
        "source_file": data.get("source_file"),
        "is_available": data.get("is_available", True),
    }


@router.post("/refresh", response_model=ETArticlesResponse)
def refresh_et_brand_equity_articles():
    """
    Triggers a live scrape refresh of ET BrandEquity, updates scraper_output/et_brand_equity.json,
    and returns the updated articles.
    """
    data = run_et_brand_equity_refresh()
    return data

