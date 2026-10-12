"""
Media Reporting System - Backend Entry Point
FastAPI application serving both REST API endpoints and the built-in enterprise dashboard.
Zero Node.js required.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("media-api")

# ---------------------------------------------------------------------------
# Ensure the project root (parent of backend/) is on sys.path so that the
# top-level 'database' package is importable regardless of how the server
# is launched (run_server.py, uvicorn CLI, or direct python invocation).
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
_PROJECT_ROOT = _BACKEND_DIR.parent                   # .../media-reporting-system
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _initialize_database() -> None:
    """
    Idempotent Phase 4 schema initialization.
    Uses CREATE TABLE IF NOT EXISTS — safe to call on every startup.
    No data is deleted or reset.
    """
    try:
        from database.schema import init_db
        init_db()
        logger.info("Database schema initialized successfully.")
    except Exception as exc:
        logger.error("Database schema initialization failed: %s", exc)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Startup order:
      1. Database connection / schema initialization
      2. Phase 5 monitoring scheduler
      3. API availability
    """
    _initialize_database()

    # Start the Phase 5 automatic monitoring scheduler
    try:
        from monitoring import scheduler as _sched
        _sched.start(run_initial_cycle=True)
    except Exception as exc:
        logger.warning("Monitoring scheduler failed to start: %s", exc)

    yield

    # Shutdown: stop the scheduler cleanly
    try:
        from monitoring import scheduler as _sched
        _sched.stop()
    except Exception as exc:
        logger.warning("Monitoring scheduler shutdown notice: %s", exc)



from app.core.config import settings          # noqa: E402 (after sys.path fix)
from app.api.endpoints import api_router      # noqa: E402

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API and Dashboard for local Media Reporting and Monitoring System",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API endpoints under /api
app.include_router(api_router, prefix=settings.API_PREFIX)

# Static files path
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_PATH = os.path.join(STATIC_DIR, "index.html")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Storage path for advertisement creative assets
STORAGE_DIR = os.path.join(str(_PROJECT_ROOT), "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")



@app.get("/")
async def root():
    """Serves the dashboard directly at root URL."""
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": f"{settings.API_PREFIX}/health",
        "dashboard": f"{settings.API_PREFIX}/dashboard",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

