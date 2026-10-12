"""
Health check endpoint.
"""
from fastapi import APIRouter
from app.schemas.dashboard import HealthResponse

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Returns system health status.
    Expected: {"status": "ok", "service": "media-reporting-system"}
    """
    return HealthResponse()
