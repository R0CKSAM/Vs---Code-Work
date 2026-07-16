from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import DatasetService, init_service, router


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
PARQUET_PATH = OUTPUT_DIR / "master_frequency.parquet"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(
        title="TV Channel Frequency Comparison Dashboard",
        version="1.0.0",
        description="Production-ready backend for week-wise TV channel frequency comparison.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    service = DatasetService(DATA_DIR, PARQUET_PATH)
    init_service(service)

    @app.on_event("startup")
    def startup_event() -> None:
        service.refresh(force=False)

    app.include_router(router)
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
