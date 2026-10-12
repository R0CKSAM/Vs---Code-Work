"""
Media Reporting System - Storyboard18 Articles Endpoint
"""
from typing import Optional
from fastapi import APIRouter, Query

from app.schemas.dashboard import SourceArticlesResponse
from app.services.generic_source_service import load_source_data, run_source_refresh

router = APIRouter(prefix="/monitoring/storyboard18", tags=["Storyboard18 Monitoring"])

WEBSITE_KEY = "storyboard18"
WEBSITE_NAME = "Storyboard18"
BASE_URL = "https://www.storyboard18.com/"


@router.get("/articles", response_model=SourceArticlesResponse)
async def get_storyboard18_articles(
    section: Optional[str] = Query(None, description="Filter articles by editorial section"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum articles; omitted returns all"),
    skip: int = Query(0, ge=0, description="Number of articles to skip"),
):
    """
    Returns verified real articles from Storyboard18.
    """
    data = load_source_data(WEBSITE_KEY, WEBSITE_NAME, BASE_URL)
    articles = data["articles"]
    if section and section.lower() != "all":
        articles = [a for a in articles if a.get("section", "").lower() == section.lower()]

    paginated = articles[skip:] if limit is None else articles[skip : skip + limit]

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
def refresh_storyboard18_articles():
    """
    Triggers a live scrape refresh of Storyboard18 and returns the updated articles.
    """
    return run_source_refresh(WEBSITE_KEY, WEBSITE_NAME, BASE_URL)
