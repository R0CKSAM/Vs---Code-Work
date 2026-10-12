"""
health.py – Diagnostic & Database Health Endpoint.

Exposes:
- GET /health: Basic service heartbeat
- GET /health/db: Database connectivity and table status check
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter
from sqlalchemy import text

from app.database.connection import create_db_engine
from app.database.migrations import get_existing_tables, verify_schema

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, str]:
    """Basic health heartbeat."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db() -> Dict[str, Any]:
    """
    Check database connectivity and table initialization status.
    Returns status: ok, database: connected, tables: true/false.
    """
    try:
        engine = create_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        tables = get_existing_tables(engine)
        schema_ok = verify_schema(engine)

        return {
            "status": "ok",
            "database": "connected",
            "tables": schema_ok,
            "table_count": len(tables),
        }
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return {
            "status": "error",
            "database": "disconnected",
            "tables": False,
            "error": str(exc),
        }
