"""
app.py – Minimal FastAPI application for Phase 2 diagnostic endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(
    title="FanCode Monitor API",
    description="Diagnostic & health monitoring API for FanCode Monitor system",
    version="0.2.0",
)

app.include_router(health_router)
