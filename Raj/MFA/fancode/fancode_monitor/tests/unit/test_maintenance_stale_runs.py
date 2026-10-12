"""
test_maintenance_stale_runs.py – Unit tests for stale execution recovery (Phase 11).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import pytest
from app.database.connection import utc_now
from app.database.models import ScrapeRun
from app.maintenance.stale_runs import reclaim_stale_runs


class TestStaleRunsRecovery:
    def test_active_run_under_threshold_is_preserved(self, db_session):
        # Run started 60 seconds ago (fresh)
        run = ScrapeRun(
            run_type="monitor",
            status="running",
            started_at=utc_now() - timedelta(seconds=60),
        )
        db_session.add(run)
        db_session.commit()

        reclaimed = reclaim_stale_runs(session=db_session, timeout_seconds=1800)
        assert len(reclaimed) == 0

        db_session.refresh(run)
        assert run.status == "running"

    def test_stale_run_over_threshold_is_reclaimed(self, db_session):
        # Run started 2 hours ago
        stale_run = ScrapeRun(
            run_type="monitor",
            status="running",
            started_at=utc_now() - timedelta(hours=2),
            metadata_json={"pid": 99999999},  # non-existent dead PID
        )
        db_session.add(stale_run)
        db_session.commit()

        reclaimed = reclaim_stale_runs(session=db_session, timeout_seconds=1800)
        assert stale_run.id in reclaimed

        db_session.refresh(stale_run)
        assert stale_run.status == "stale_reclaimed"
        assert stale_run.finished_at is not None
        assert "Stale run reclaimed" in stale_run.error_message
        assert stale_run.metadata_json.get("reclaimed_reason") is not None

    def test_active_pid_ownership_prevents_reclamation(self, db_session):
        # Run has current process PID (alive)
        run = ScrapeRun(
            run_type="monitor",
            status="running",
            started_at=utc_now() - timedelta(hours=2),
            metadata_json={"pid": os.getpid()},
        )
        db_session.add(run)
        db_session.commit()

        reclaimed = reclaim_stale_runs(session=db_session, timeout_seconds=1800)
        assert len(reclaimed) == 0

        db_session.refresh(run)
        assert run.status == "running"
