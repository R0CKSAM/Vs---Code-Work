"""
Media Reporting System - Indian Television Articles Endpoint
"""
from typing import Optional
from fastapi import APIRouter, Query

from app.schemas.dashboard import SourceArticlesResponse
from app.services.generic_source_service import load_source_data, run_source_refresh

router = APIRouter(prefix="/monitoring/indiantelevision", tags=["Indian Television Monitoring"])

WEBSITE_KEY = "indiantelevision"
WEBSITE_NAME = "Indian Television"
BASE_URL = "https://indiantelevision.com/"


@router.get("/articles", response_model=SourceArticlesResponse)
async def get_indiantelevision_articles(
    section: Optional[str] = Query(None, description="Filter articles by editorial section"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of articles to return"),
    skip: int = Query(0, ge=0, description="Number of articles to skip"),
):
    """
    Returns verified real articles from Indian Television.
    """
    data = load_source_data(WEBSITE_KEY, WEBSITE_NAME, BASE_URL)
    articles = data["articles"]
    if section and section.lower() != "all":
        articles = [a for a in articles if a.get("section", "").lower() == section.lower()]

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


@router.post("/refresh", response_model=SourceArticlesResponse)
def refresh_indiantelevision_articles():
    """
    Triggers a live scrape refresh of Indian Television and returns the updated articles.
    """
    return run_source_refresh(WEBSITE_KEY, WEBSITE_NAME, BASE_URL)
