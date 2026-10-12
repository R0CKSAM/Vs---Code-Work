"""
Dashboard data endpoint.
"""
from fastapi import APIRouter
from app.schemas.dashboard import DashboardResponse
from app.services.mock_data import get_mock_dashboard_data

router = APIRouter(tags=["Dashboard"])

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard():
    """
    Returns dashboard overview metrics, website monitoring statuses,
    latest news articles, and tracked advertisements.
    Phase 0 utilizes structured mock data pending scraper and DB integrations.
    """
    return get_mock_dashboard_data()
