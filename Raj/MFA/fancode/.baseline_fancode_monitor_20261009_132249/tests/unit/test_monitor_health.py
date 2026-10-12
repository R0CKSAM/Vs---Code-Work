"""
test_monitor_health.py – Unit tests for MonitorHealth status reporting (Phase 10).
"""

from __future__ import annotations

import pytest
from app.database.models import ScrapeRun
from app.monitor.health import MonitorHealth


class TestMonitorHealth:
    def test_health_status_empty_db(self, db_session):
        status = MonitorHealth.get_status(session=db_session)
        assert status["health"] == "HEALTHY"
        assert status["monitor_enabled"] is True
        assert status["lock"]["is_locked"] is False
        assert status["latest_run"] is None

        text = MonitorHealth.format_text(status)
        assert "FanCode Monitor — System Status & Health" in text
        assert "No monitor runs recorded yet" in text

    def test_health_status_with_run_record(self, db_session):
        repo_run = ScrapeRun(
            run_type="monitor",
            status="success",
            records_processed=50,
            changes_detected=3,
        )
        db_session.add(repo_run)
        db_session.commit()

        status = MonitorHealth.get_status(session=db_session)
        assert status["health"] == "HEALTHY"
        assert status["latest_run"] is not None
        assert status["latest_run"]["records_processed"] == 50
        assert status["latest_run"]["changes_detected"] == 3

        text = MonitorHealth.format_text(status)
        assert "Run ID           : #" in text
        assert "Records Checked  : 50" in text
        assert "Changes Detected : 3" in text

    def test_health_status_degraded_on_failed_latest_run(self, db_session):
        failed_run = ScrapeRun(
            run_type="monitor",
            status="failed",
            error_message="Simulated run failure",
        )
        db_session.add(failed_run)
        db_session.commit()

        status = MonitorHealth.get_status(session=db_session)
        assert status["health"] == "DEGRADED"
        assert status["status"] == "degraded"
        assert status["last_failure"] is not None

    def test_health_status_unhealthy_on_broken_db_session(self):
        class BrokenSession:
            def execute(self, *args, **kwargs):
                raise RuntimeError("Database connection dropped")
            def get_bind(self):
                raise RuntimeError("Database connection dropped")

        status = MonitorHealth.get_status(session=BrokenSession())
        assert status["health"] == "UNHEALTHY"
        assert status["status"] == "unhealthy"
        assert status["database"] == "failed"
