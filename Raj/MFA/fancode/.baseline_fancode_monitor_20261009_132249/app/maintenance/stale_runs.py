"""
stale_runs.py – Stale Execution Recovery for FanCode Scrape & Monitor Runs (Phase 11).

Finds runs left in 'running' state past the configured timeout threshold and marks them
'stale_reclaimed' with audit metadata, ensuring no genuinely active runs are reclaimed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.connection import utc_now
from app.database.models import ScrapeRun
from app.monitor.lock import is_process_alive

logger = logging.getLogger(__name__)


def reclaim_stale_runs(
    session: Session,
    timeout_seconds: Optional[int] = None,
    active_pid: Optional[int] = None,
) -> List[int]:
    """
    Identifies runs left in 'running' status older than timeout_seconds and safely
    marks them 'stale_reclaimed'.

    Never marks a run stale if its PID is active and matching active_pid.
    Returns list of reclaimed ScrapeRun IDs.
    """
    threshold = timeout_seconds or getattr(settings, "STALE_RUN_TIMEOUT_SECONDS", 1800)
    now = utc_now()

    stmt = select(ScrapeRun).where(ScrapeRun.status == "running")
    running_runs = list(session.scalars(stmt).all())

    reclaimed_ids: List[int] = []

    for run in running_runs:
        if not run.started_at:
            continue

        started_at = run.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        age = (now - started_at).total_seconds()
        if age < threshold:
            # Still within legitimate run window
            continue

        # Check PID ownership if recorded in metadata
        run_meta = run.metadata_json or {}
        run_pid = run_meta.get("pid")
        if run_pid and is_process_alive(int(run_pid)):
            # Process is genuinely alive!
            continue

        # Safe to reclaim
        logger.warning(
            "Reclaiming stale run #%d (type=%s, age=%.1fs > threshold=%ds)...",
            run.id,
            run.run_type,
            age,
            threshold,
        )
        run.status = "stale_reclaimed"
        run.finished_at = now
        run.error_message = f"Stale run reclaimed after {int(age)}s without completion"

        updated_meta = dict(run_meta)
        updated_meta["reclaimed_at"] = now.isoformat()
        updated_meta["reclaimed_reason"] = f"timed_out_after_{int(age)}s"
        run.metadata_json = updated_meta

        reclaimed_ids.append(run.id)

    if reclaimed_ids:
        session.commit()
        logger.info("Reclaimed %d stale run(s): %s", len(reclaimed_ids), reclaimed_ids)

    return reclaimed_ids
