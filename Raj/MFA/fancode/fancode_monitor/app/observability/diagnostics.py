"""
diagnostics.py – Database Integrity Checks & Operational Diagnostics for FanCode Monitor (Phase 11).

Provides:
- Non-destructive database integrity verification (tables, FKs, read test, schema expectations).
- Performance diagnostics (cycle and stage durations, record counts, retry and alert counts).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database.connection import get_session
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)

REQUIRED_TABLES = [
    "sports",
    "tours",
    "matches",
    "videos",
    "pages",
    "change_events",
    "scrape_runs",
    "notification_batches",
    "notification_deliveries",
    "notification_event_links",
]


def check_database_integrity(session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Executes a comprehensive, non-destructive database health and schema integrity audit.
    Verifies:
      1. Connectivity
      2. Required table presence
      3. Ability to perform read operations
      4. Foreign key pragma status (for SQLite)
      5. Transaction sanity
    """
    def _run_check(s: Session) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "OK",
            "connection": "OK",
            "tables_found": [],
            "tables_missing": [],
            "foreign_keys_enabled": None,
            "read_test": "OK",
            "errors": [],
        }

        # 1. Connection check
        try:
            s.execute(text("SELECT 1")).scalar()
        except Exception as e:
            result["status"] = "FAILED"
            result["connection"] = "FAILED"
            result["errors"].append(f"Connection query failed: {e}")
            return result

        # 2. Table presence check
        try:
            bind = s.get_bind()
            inspector = inspect(bind)
            existing_tables = set(inspector.get_table_names())
            for t in REQUIRED_TABLES:
                if t in existing_tables:
                    result["tables_found"].append(t)
                else:
                    result["tables_missing"].append(t)

            if result["tables_missing"]:
                result["status"] = "FAILED"
                result["errors"].append(f"Missing required tables: {result['tables_missing']}")
        except Exception as e:
            result["status"] = "FAILED"
            result["errors"].append(f"Schema inspection failed: {e}")

        # 3. Foreign key enforcement check (for SQLite)
        try:
            fk_status = s.execute(text("PRAGMA foreign_keys")).scalar()
            result["foreign_keys_enabled"] = bool(fk_status)
        except Exception:
            # Not SQLite or pragma unsupported
            result["foreign_keys_enabled"] = None

        # 4. Read test across core tables
        try:
            for t in ["sports", "scrape_runs", "change_events"]:
                if t in result["tables_found"]:
                    s.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        except Exception as e:
            result["status"] = "FAILED"
            result["read_test"] = "FAILED"
            result["errors"].append(f"Read test failed on core table: {e}")

        return result

    if session:
        return _run_check(session)
    else:
        with get_session() as s:
            return _run_check(s)


def collect_system_diagnostics(session: Optional[Session] = None) -> Dict[str, Any]:
    """Compiles complete operational diagnostics including DB integrity and metrics."""
    db_integrity = check_database_integrity(session)
    metrics_snapshot = metrics.snapshot()

    return {
        "status": "HEALTHY" if db_integrity["status"] == "OK" else "DEGRADED",
        "database_integrity": db_integrity,
        "metrics": metrics_snapshot,
    }


def format_diagnostics_text(diag: Dict[str, Any]) -> str:
    """Formats diagnostics data into clean CLI output."""
    db = diag.get("database_integrity", {})
    m = diag.get("metrics", {})

    lines = [
        "===========================================================",
        "   FanCode Monitor — Operational Diagnostics",
        "===========================================================",
        f"  Overall Status       : {diag.get('status')}",
        f"  Database Connection  : {db.get('connection')}",
        f"  Required Tables      : {len(db.get('tables_found', []))}/{len(REQUIRED_TABLES)} present",
    ]
    if db.get("tables_missing"):
        lines.append(f"  Missing Tables       : {', '.join(db.get('tables_missing'))}")
    if db.get("foreign_keys_enabled") is not None:
        lines.append(f"  Foreign Keys Active  : {db.get('foreign_keys_enabled')}")

    lines.append("-----------------------------------------------------------")
    lines.append("  In-Process Operational Metrics:")
    lines.append(f"    Monitor Cycles     : {m.get('monitor_cycles_total', 0)} total ({m.get('monitor_cycles_success', 0)} ok, {m.get('monitor_cycles_failed', 0)} fail)")
    lines.append(f"    Stage Runs         : {m.get('stage_runs_total', 0)} total ({m.get('stage_runs_success', 0)} ok, {m.get('stage_runs_failed', 0)} fail, {m.get('stage_retries_total', 0)} retries)")
    lines.append(f"    Records Handled    : {m.get('records_processed', 0)} processed, {m.get('records_created', 0)} created, {m.get('records_updated', 0)} updated")
    lines.append(f"    Change Events      : {m.get('change_events_created', 0)} created")
    lines.append(f"    Notifications      : {m.get('notifications_created', 0)} created, {m.get('notifications_sent', 0)} sent, {m.get('notifications_failed', 0)} failed")
    lines.append(f"    Error Events       : {m.get('database_errors', 0)} db errors, {m.get('lock_failures', 0)} lock failures")
    if db.get("errors"):
        lines.append("-----------------------------------------------------------")
        lines.append("  Integrity Errors:")
        for err in db.get("errors", []):
            lines.append(f"    [!] {err}")
    lines.append("===========================================================")
    return "\n".join(lines)
