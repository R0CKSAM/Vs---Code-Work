"""
Media Reporting System - Phase 5 Monitoring Status & Control Endpoints
GET  /api/monitoring/status   — returns current scheduler & per-website state
POST /api/monitoring/run-now  — manually triggers one monitoring cycle
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/monitoring", tags=["Monitoring Engine"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class WebsiteMonitorStatus(BaseModel):
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_status: str = "PENDING"
    last_article_count: int = 0
    last_error: Optional[str] = None


class MonitoringStatusResponse(BaseModel):
    scheduler_enabled: bool
    interval_minutes: int
    scheduler_started_at: Optional[str] = None
    last_cycle_started_at: Optional[str] = None
    last_cycle_completed_at: Optional[str] = None
    last_cycle_status: Optional[str] = None
    next_run_at: Optional[str] = None
    currently_running: bool
    total_cycles: int
    successful_cycles: int
    failed_cycles: int
    partial_cycles: int = 0
    websites: Dict[str, WebsiteMonitorStatus]


class RunNowResponse(BaseModel):
    status: str          # "started" | "already_running"
    message: str = ""


# ---------------------------------------------------------------------------
# GET /api/monitoring/status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=MonitoringStatusResponse)
async def get_monitoring_status():
    """
    Returns the current operational state of the Phase 5 monitoring scheduler
    and per-website refresh results.
    """
    from monitoring.status import monitoring_status
    snap = monitoring_status.snapshot()

    websites_out: Dict[str, WebsiteMonitorStatus] = {}
    for key, ws in snap.get("websites", {}).items():
        websites_out[key] = WebsiteMonitorStatus(**ws)

    return MonitoringStatusResponse(
        scheduler_enabled=snap["scheduler_enabled"],
        interval_minutes=snap["interval_minutes"],
        scheduler_started_at=snap.get("scheduler_started_at"),
        last_cycle_started_at=snap.get("last_cycle_started_at"),
        last_cycle_completed_at=snap.get("last_cycle_completed_at"),
        last_cycle_status=snap.get("last_cycle_status"),
        next_run_at=snap.get("next_run_at"),
        currently_running=snap["currently_running"],
        total_cycles=snap["total_cycles"],
        successful_cycles=snap["successful_cycles"],
        failed_cycles=snap["failed_cycles"],
        partial_cycles=snap.get("partial_cycles", 0),
        websites=websites_out,
    )


# ---------------------------------------------------------------------------
# POST /api/monitoring/run-now
# ---------------------------------------------------------------------------

@router.post("/run-now", response_model=RunNowResponse)
async def run_monitoring_now():
    """
    Manually triggers one monitoring cycle.
    Returns immediately; the cycle runs in a background thread.
    Does nothing if a cycle is already running.
    """
    from monitoring.status import monitoring_status
    from monitoring.engine import run_monitoring_cycle

    if monitoring_status.is_running():
        return RunNowResponse(
            status="already_running",
            message="A monitoring cycle is currently in progress. Try again shortly.",
        )

    t = threading.Thread(target=run_monitoring_cycle, name="monitor-manual", daemon=True)
    t.start()
    return RunNowResponse(
        status="started",
        message="Monitoring cycle started in background.",
    )
