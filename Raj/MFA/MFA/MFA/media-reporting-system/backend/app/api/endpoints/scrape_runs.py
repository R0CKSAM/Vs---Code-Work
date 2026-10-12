"""
Media Reporting System - Scrape Runs Audit Endpoints (Phase 4)
"""
from typing import Optional
from fastapi import APIRouter, Query

from app.schemas.dashboard import ScrapeRunsResponse
from database.repository import db_repo

router = APIRouter(prefix="/monitoring", tags=["Scraper Audit Runs"])


@router.get("/scrape-runs", response_model=ScrapeRunsResponse)
async def get_all_scrape_runs(
    website: Optional[str] = Query(None, description="Filter by website key (e.g. et_brand_equity, exchange4media)"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Returns recent scrape run audits with status, duration, and article change statistics.
    """
    website_key = None if website in (None, "all", "") else website
    runs = db_repo.get_recent_scrape_runs(website_key=website_key, limit=limit)
    return {
        "count": len(runs),
        "runs": runs,
    }


@router.get("/{website}/scrape-runs", response_model=ScrapeRunsResponse)
async def get_website_scrape_runs(
    website: str,
    limit: int = Query(20, ge=1, le=100),
):
    """
    Returns recent scrape run audits for a specific website.
    """
    return await get_all_scrape_runs(website=website, limit=limit)
