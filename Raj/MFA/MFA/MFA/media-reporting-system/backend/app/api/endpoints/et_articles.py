"""
Media Reporting System - ET BrandEquity Articles Endpoint (Phase 2B)
"""
from fastapi import APIRouter, HTTPException
from app.schemas.dashboard import ETArticlesResponse
from app.services.et_brand_equity_service import (
    load_et_brand_equity_data,
    run_et_brand_equity_refresh,
)

router = APIRouter(prefix="/monitoring/et-brand-equity", tags=["ET BrandEquity Monitoring"])


@router.get("/articles", response_model=ETArticlesResponse)
async def get_et_brand_equity_articles():
    """
    Returns verified real articles from ET BrandEquity extracted during Phase 2A scraping.
    Source of truth: scraper_output/et_brand_equity.json
    """
    data = load_et_brand_equity_data()
    return data


@router.post("/refresh", response_model=ETArticlesResponse)
def refresh_et_brand_equity_articles():
    """
    Triggers a live scrape refresh of ET BrandEquity, updates scraper_output/et_brand_equity.json,
    and returns the updated articles.
    """
    data = run_et_brand_equity_refresh()
    return data

