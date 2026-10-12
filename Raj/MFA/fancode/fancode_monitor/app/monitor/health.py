"""
health.py – Comprehensive health check and status reporting for FanCode Monitor (Phase 10 & 11).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.connection import get_session
from app.database.models import ScrapeRun
from app.database.repositories import ScrapeRunsRepository
from app.monitor.lock import MonitorLock
from app.observability.diagnostics import check_database_integrity
from app.observability.heartbeat import heartbeat

logger = logging.getLogger(__name__)


class MonitorHealth:
    """
    Inspects monitor lock state, database integrity, heartbeat, recent runs,
    and pipeline execution health across HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN states.
    """

    @classmethod
    def get_status(cls, session: Optional[Session] = None) -> Dict[str, Any]:
        """
        Compiles current health, database integrity, and operational metrics.
        """
        lock = MonitorLock()
        is_locked = lock.is_locked()
        lock_info = lock.get_lock_info()
        hb_data = heartbeat.read() or {}

        def _fetch_status(s: Session) -> Dict[str, Any]:
            # 1. Database integrity
            db_audit = check_database_integrity(s)
            db_ok = db_audit["status"] == "OK"

            # 2. Run history
            repo = ScrapeRunsRepository(s)
            latest_run = repo.get_latest(run_type="monitor")
            recent_runs = repo.get_recent(limit=10)

            # Last success / failure queries
            stmt_success = (
                select(ScrapeRun)
                .where(ScrapeRun.run_type == "monitor", ScrapeRun.status == "success")
                .order_by(desc(ScrapeRun.started_at))
                .limit(1)
            )
            last_success_run = s.scalars(stmt_success).first()

            stmt_failure = (
                select(ScrapeRun)
                .where(ScrapeRun.run_type == "monitor", ScrapeRun.status.in_(["failed", "stale_reclaimed"]))
                .order_by(desc(ScrapeRun.started_at))
                .limit(1)
            )
            last_failure_run = s.scalars(stmt_failure).first()

            latest_run_dict = None
            if latest_run:
                duration = (
                    (latest_run.finished_at - latest_run.started_at).total_seconds()
                    if latest_run.finished_at and latest_run.started_at
                    else 0.0
                )
                latest_run_dict = {
                    "id": latest_run.id,
                    "status": latest_run.status,
                    "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                    "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
                    "duration_seconds": round(duration, 2),
                    "records_processed": latest_run.records_processed,
                    "changes_detected": latest_run.changes_detected,
                    "errors_count": latest_run.errors_count,
                    "error_message": latest_run.error_message,
                }

            # 3. Overall health status determination
            if not db_ok:
                overall_health = "UNHEALTHY"
            elif latest_run and latest_run.status in ("failed", "stale_reclaimed"):
                overall_health = "DEGRADED"
            elif is_locked and hb_data.get("stage") != "idle":
                overall_health = "RUNNING"
            else:
                overall_health = "HEALTHY"

            status_val = overall_health.lower()

            return {
                "health": overall_health,
                "status": status_val,
                "database": "ok" if db_ok else "failed",
                "database_integrity": db_audit,
                "monitor_enabled": getattr(settings, "MONITOR_ENABLED", True),
                "lock": {
                    "is_locked": is_locked,
                    "status": "active" if is_locked else "available",
                    "info": lock_info,
                },
                "heartbeat": {
                    "active": heartbeat.is_fresh(),
                    "data": hb_data,
                },
                "current_stage": hb_data.get("stage"),
                "uptime_seconds": hb_data.get("uptime_seconds", 0.0),
                "cycles_completed": hb_data.get("cycle", 0),
                "latest_run": latest_run_dict,
                "last_run": latest_run_dict.get("started_at") if latest_run_dict else None,
                "last_success": last_success_run.started_at.isoformat() if last_success_run and last_success_run.started_at else None,
                "last_failure": last_failure_run.started_at.isoformat() if last_failure_run and last_failure_run.started_at else None,
                "recent_runs_count": len(recent_runs),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        try:
            if session:
                return _fetch_status(session)
            else:
                with get_session() as s:
                    return _fetch_status(s)
        except Exception as e:
            logger.error("Health evaluation failed: %s", e)
            return {
                "health": "UNHEALTHY",
                "status": "unhealthy",
                "database": "failed",
                "monitor_enabled": getattr(settings, "MONITOR_ENABLED", True),
                "lock": {"is_locked": is_locked, "info": lock_info},
                "latest_run": None,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    @classmethod
    def format_text(cls, status: Dict[str, Any]) -> str:
        """Formats the status dictionary into human-readable text."""
        lines = [
            "===========================================================",
            "   FanCode Monitor — System Status & Health",
            "===========================================================",
            f"  Health Status      : {status.get('health')}",
            f"  Database           : {status.get('database')}",
            f"  Monitor Enabled    : {status.get('monitor_enabled')}",
            f"  Lock Active        : {status.get('lock', {}).get('is_locked')}",
        ]

        lock_info = status.get("lock", {}).get("info")
        if lock_info:
            lines.append(f"  Lock Holder (PID)  : {lock_info.get('pid')} (Run: {lock_info.get('run_id')})")

        if status.get("current_stage"):
            lines.append(f"  Current Stage      : {status.get('current_stage')}")
        if status.get("cycles_completed"):
            lines.append(f"  Cycles Completed   : {status.get('cycles_completed')}")
        if status.get("last_success"):
            lines.append(f"  Last Success       : {status.get('last_success')}")
        if status.get("last_failure"):
            lines.append(f"  Last Failure       : {status.get('last_failure')}")

        latest = status.get("latest_run")
        if latest:
            lines.append("-----------------------------------------------------------")
            lines.append("  Latest Run Details:")
            lines.append(f"    Run ID           : #{latest.get('id')}")
            lines.append(f"    Status           : {latest.get('status')}")
            lines.append(f"    Started At       : {latest.get('started_at')}")
            lines.append(f"    Duration         : {latest.get('duration_seconds')}s")
            lines.append(f"    Records Checked  : {latest.get('records_processed')}")
            lines.append(f"    Changes Detected : {latest.get('changes_detected')}")
            lines.append(f"    Errors           : {latest.get('errors_count')}")
            if latest.get("error_message"):
                lines.append(f"    Error Message    : {latest.get('error_message')}")
        else:
            lines.append("-----------------------------------------------------------")
            lines.append("  Latest Run Details : No monitor runs recorded yet.")

        lines.append("===========================================================")
        return "\n".join(lines)
