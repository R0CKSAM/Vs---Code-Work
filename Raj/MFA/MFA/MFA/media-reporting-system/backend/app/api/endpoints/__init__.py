"""
Media Reporting System - API Endpoints Registry
"""
from fastapi import APIRouter
from .health import router as health_router
from .dashboard import router as dashboard_router
from .et_articles import router as et_articles_router
from .exchange4media_articles import router as exchange4media_articles_router
from .campaign_india_articles import router as campaign_india_articles_router
from .bestmediainfo_articles import router as bestmediainfo_articles_router
from .social_samosa_articles import router as social_samosa_articles_router
from .adgully_articles import router as adgully_articles_router
from .mediabrief_articles import router as mediabrief_articles_router
from .storyboard18_articles import router as storyboard18_articles_router
from .indiantelevision_articles import router as indiantelevision_articles_router
from .changes import router as changes_router
from .scrape_runs import router as scrape_runs_router
from .monitoring import router as monitoring_router
from .advertisements import router as advertisements_router
from .reports import router as reports_router
from .auth import router as auth_router
from .admin import router as admin_router
from .news import router as news_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(news_router)
api_router.include_router(dashboard_router)
api_router.include_router(et_articles_router)
api_router.include_router(exchange4media_articles_router)
api_router.include_router(campaign_india_articles_router)
api_router.include_router(bestmediainfo_articles_router)
api_router.include_router(social_samosa_articles_router)
api_router.include_router(adgully_articles_router)
api_router.include_router(mediabrief_articles_router)
api_router.include_router(storyboard18_articles_router)
api_router.include_router(indiantelevision_articles_router)
api_router.include_router(changes_router)
api_router.include_router(scrape_runs_router)
api_router.include_router(monitoring_router)
api_router.include_router(advertisements_router)
api_router.include_router(reports_router)

__all__ = [
    "api_router",
    "campaign_india_articles_router",
    "bestmediainfo_articles_router",
    "social_samosa_articles_router",
    "adgully_articles_router",
    "mediabrief_articles_router",
    "storyboard18_articles_router",
    "indiantelevision_articles_router",
]
