"""
Media Reporting System - Phase 5 Monitoring Status Store
In-memory operational state tracking for the scheduler.
Historical audit data remains in scrape_runs DB table.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Per-website status record
# ---------------------------------------------------------------------------
_DEFAULT_WEBSITE_STATUS: Dict[str, Any] = {
    "last_attempt_at": None,
    "last_success_at": None,
    "last_status": "PENDING",   # PENDING | SUCCESS | FAILED
    "last_article_count": 0,
    "last_error": None,
}

_WEBSITE_KEYS = [
    "et_brand_equity",
    "exchange4media",
    "campaign_india",
    "bestmediainfo",
    "social_samosa",
    "adgully",
    "mediabrief",
    "storyboard18",
    "indiantelevision",
]


class MonitoringStatus:
    """
    Thread-safe in-memory monitoring status store.
    Tracks scheduler state and last known per-website result.
    """

    def __init__(self, interval_minutes: int = 10) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "scheduler_enabled": False,
            "interval_minutes": interval_minutes,
            "scheduler_started_at": None,
            "last_cycle_started_at": None,
            "last_cycle_completed_at": None,
            "last_cycle_status": None,       # SUCCESS | PARTIAL_SUCCESS | FAILED | RUNNING
            "next_run_at": None,
            "currently_running": False,
            "total_cycles": 0,
            "successful_cycles": 0,
            "failed_cycles": 0,
            "partial_cycles": 0,
            "websites": {
                key: dict(_DEFAULT_WEBSITE_STATUS) for key in _WEBSITE_KEYS
            },
        }

    # -----------------------------------------------------------------------
    # Scheduler lifecycle
    # -----------------------------------------------------------------------
    def mark_scheduler_started(self, interval_minutes: int) -> None:
        with self._lock:
            self._state["scheduler_enabled"] = True
            self._state["interval_minutes"] = interval_minutes
            self._state["scheduler_started_at"] = _now_iso()

    def mark_scheduler_stopped(self) -> None:
        with self._lock:
            self._state["scheduler_enabled"] = False
            self._state["next_run_at"] = None

    def set_next_run_at(self, dt: Optional[datetime]) -> None:
        with self._lock:
            self._state["next_run_at"] = dt.isoformat() if dt else None

    # -----------------------------------------------------------------------
    # Cycle lifecycle
    # -----------------------------------------------------------------------
    def mark_cycle_started(self) -> None:
        with self._lock:
            self._state["currently_running"] = True
            self._state["last_cycle_started_at"] = _now_iso()
            self._state["last_cycle_status"] = "RUNNING"
            self._state["total_cycles"] += 1

    def mark_cycle_completed(self, status: str) -> None:
        """
        status: SUCCESS | PARTIAL_SUCCESS | FAILED
        """
        with self._lock:
            self._state["currently_running"] = False
            self._state["last_cycle_completed_at"] = _now_iso()
            self._state["last_cycle_status"] = status
            if status == "SUCCESS":
                self._state["successful_cycles"] += 1
            elif status == "FAILED":
                self._state["failed_cycles"] += 1
            else:
                self._state["partial_cycles"] += 1

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._state["currently_running"])

    # -----------------------------------------------------------------------
    # Per-website updates
    # -----------------------------------------------------------------------
    def mark_website_attempt(self, website_key: str) -> None:
        with self._lock:
            if website_key in self._state["websites"]:
                self._state["websites"][website_key]["last_attempt_at"] = _now_iso()
                self._state["websites"][website_key]["last_status"] = "RUNNING"

    def mark_website_success(self, website_key: str, article_count: int) -> None:
        with self._lock:
            if website_key in self._state["websites"]:
                now = _now_iso()
                self._state["websites"][website_key]["last_success_at"] = now
                self._state["websites"][website_key]["last_status"] = "SUCCESS"
                self._state["websites"][website_key]["last_article_count"] = article_count
                self._state["websites"][website_key]["last_error"] = None

    def mark_website_failed(self, website_key: str, error: str) -> None:
        with self._lock:
            if website_key in self._state["websites"]:
                self._state["websites"][website_key]["last_status"] = "FAILED"
                self._state["websites"][website_key]["last_error"] = str(error)

    # -----------------------------------------------------------------------
    # Read snapshot (returns a deep copy safe for serialization)
    # -----------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        import copy
        with self._lock:
            return copy.deepcopy(self._state)


# Global singleton — imported by scheduler, endpoints, and main
monitoring_status = MonitoringStatus()
