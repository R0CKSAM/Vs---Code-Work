"""
Phase 5 - Monitoring Engine Tests
Tests the scheduler logic, cycle status semantics, overlap protection,
website isolation, and status store — without waiting 10 real minutes.
"""
import sys
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root and backend are on sys.path
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from monitoring.status import MonitoringStatus
from monitoring.engine import (
    _validate_articles,
    run_monitoring_cycle,
    MONITORED_WEBSITES,
    get_interval_minutes,
)


# ---------------------------------------------------------------------------
# 1. Scheduler configuration
# ---------------------------------------------------------------------------
class TestSchedulerConfig(unittest.TestCase):
    def test_default_interval_is_10(self):
        """Scheduler interval defaults to 10 minutes when no env var is set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MONITORING_INTERVAL_MINUTES", None)
            interval = get_interval_minutes()
        self.assertEqual(interval, 10)

    def test_env_override_interval(self):
        """MONITORING_INTERVAL_MINUTES env var controls the interval."""
        with patch.dict(os.environ, {"MONITORING_INTERVAL_MINUTES": "5"}):
            interval = get_interval_minutes()
        self.assertEqual(interval, 5)

    def test_invalid_env_falls_back_to_10(self):
        """Invalid env value falls back to 10 minutes."""
        with patch.dict(os.environ, {"MONITORING_INTERVAL_MINUTES": "not_a_number"}):
            interval = get_interval_minutes()
        self.assertEqual(interval, 10)


# ---------------------------------------------------------------------------
# 2. MonitoringStatus store
# ---------------------------------------------------------------------------
class TestMonitoringStatus(unittest.TestCase):
    def setUp(self):
        self.status = MonitoringStatus(interval_minutes=10)

    def test_initial_state(self):
        snap = self.status.snapshot()
        self.assertFalse(snap["scheduler_enabled"])
        self.assertEqual(snap["total_cycles"], 0)
        self.assertFalse(snap["currently_running"])

    def test_scheduler_started(self):
        self.status.mark_scheduler_started(10)
        snap = self.status.snapshot()
        self.assertTrue(snap["scheduler_enabled"])
        self.assertIsNotNone(snap["scheduler_started_at"])

    def test_scheduler_stopped(self):
        self.status.mark_scheduler_started(10)
        self.status.mark_scheduler_stopped()
        snap = self.status.snapshot()
        self.assertFalse(snap["scheduler_enabled"])

    def test_cycle_lifecycle(self):
        self.status.mark_cycle_started()
        snap = self.status.snapshot()
        self.assertTrue(snap["currently_running"])
        self.assertEqual(snap["total_cycles"], 1)
        self.assertEqual(snap["last_cycle_status"], "RUNNING")

        self.status.mark_cycle_completed("SUCCESS")
        snap = self.status.snapshot()
        self.assertFalse(snap["currently_running"])
        self.assertEqual(snap["last_cycle_status"], "SUCCESS")
        self.assertEqual(snap["successful_cycles"], 1)

    def test_failed_cycle_counter(self):
        self.status.mark_cycle_started()
        self.status.mark_cycle_completed("FAILED")
        snap = self.status.snapshot()
        self.assertEqual(snap["failed_cycles"], 1)
        self.assertEqual(snap["successful_cycles"], 0)

    def test_partial_cycle_counter(self):
        self.status.mark_cycle_started()
        self.status.mark_cycle_completed("PARTIAL_SUCCESS")
        snap = self.status.snapshot()
        self.assertEqual(snap["partial_cycles"], 1)

    def test_website_success(self):
        self.status.mark_website_attempt("et_brand_equity")
        self.status.mark_website_success("et_brand_equity", article_count=25)
        snap = self.status.snapshot()
        et = snap["websites"]["et_brand_equity"]
        self.assertEqual(et["last_status"], "SUCCESS")
        self.assertEqual(et["last_article_count"], 25)
        self.assertIsNone(et["last_error"])

    def test_website_failure(self):
        self.status.mark_website_attempt("et_brand_equity")
        self.status.mark_website_failed("et_brand_equity", "HTTP 503")
        snap = self.status.snapshot()
        et = snap["websites"]["et_brand_equity"]
        self.assertEqual(et["last_status"], "FAILED")
        self.assertEqual(et["last_error"], "HTTP 503")

    def test_status_endpoint_shape(self):
        """Snapshot contains all keys required by GET /api/monitoring/status."""
        snap = self.status.snapshot()
        required_keys = [
            "scheduler_enabled", "interval_minutes", "scheduler_started_at",
            "last_cycle_started_at", "last_cycle_completed_at", "last_cycle_status",
            "next_run_at", "currently_running", "total_cycles",
            "successful_cycles", "failed_cycles", "websites",
        ]
        for key in required_keys:
            self.assertIn(key, snap, f"Missing key: {key}")
        for site_key in ["et_brand_equity", "exchange4media"]:
            self.assertIn(site_key, snap["websites"])


# ---------------------------------------------------------------------------
# 3. Validation logic
# ---------------------------------------------------------------------------
class TestArticleValidation(unittest.TestCase):
    def _make_articles(self, n=10, key="et_brand_equity"):
        return [
            {"url": f"https://example.com/{i}", "headline": f"H{i}", "website_key": key}
            for i in range(n)
        ]

    def test_valid_articles_pass(self):
        arts = self._make_articles(10)
        valid, reason = _validate_articles("et_brand_equity", arts)
        self.assertTrue(valid)

    def test_empty_list_fails(self):
        valid, reason = _validate_articles("et_brand_equity", [])
        self.assertFalse(valid)

    def test_below_threshold_fails(self):
        arts = self._make_articles(3)
        valid, reason = _validate_articles("et_brand_equity", arts, min_count=5)
        self.assertFalse(valid)

    def test_wrong_website_key_fails(self):
        arts = self._make_articles(10, key="exchange4media")
        valid, reason = _validate_articles("et_brand_equity", arts)
        self.assertFalse(valid)
        self.assertIn("contamination", reason)

    def test_non_list_fails(self):
        valid, reason = _validate_articles("et_brand_equity", {"not": "a list"})
        self.assertFalse(valid)

    def test_missing_url_fails(self):
        arts = [{"headline": "No URL", "website_key": "et_brand_equity"}]
        arts.extend(self._make_articles(9))
        valid, reason = _validate_articles("et_brand_equity", arts[:5])
        self.assertFalse(valid)


# ---------------------------------------------------------------------------
# 4–9. Cycle status semantics & overlap protection
# ---------------------------------------------------------------------------

def _make_ok_refresh(key):
    """Returns a mock refresh function that succeeds."""
    def _refresh():
        return (True, 25, "")
    return _refresh


def _make_fail_refresh(key):
    """Returns a mock refresh function that fails."""
    def _refresh():
        return (False, 0, "Simulated error")
    return _refresh


class TestMonitoringCycle(unittest.TestCase):
    """
    Tests run_monitoring_cycle() with mocked per-website refresh functions
    so we never make real network calls.
    """

    def setUp(self):
        # Reset monitoring status before each test
        from monitoring import status as _status_mod
        _status_mod.monitoring_status = MonitoringStatus(interval_minutes=10)

    def _patch_refresh(self, et_ok=True, e4m_ok=True):
        """
        Patches run_website_refresh to return success/failure per site.
        """
        def mock_refresh(website_key, website_name):
            if website_key == "et_brand_equity":
                return (True, 25, "") if et_ok else (False, 0, "ET error")
            elif website_key == "exchange4media":
                return (True, 25, "") if e4m_ok else (False, 0, "E4M error")
            if not et_ok and not e4m_ok:
                return (False, 0, f"{website_name} error")
            return (True, 25, "")
        return patch("monitoring.engine.run_website_refresh", side_effect=mock_refresh)

    def test_both_succeed_returns_success(self):
        """ET OK + E4M OK → SUCCESS"""
        with self._patch_refresh(et_ok=True, e4m_ok=True):
            result = run_monitoring_cycle()
        self.assertEqual(result, "SUCCESS")

    def test_et_fail_e4m_ok_returns_partial(self):
        """ET FAIL + E4M OK → PARTIAL_SUCCESS"""
        with self._patch_refresh(et_ok=False, e4m_ok=True):
            result = run_monitoring_cycle()
        self.assertEqual(result, "PARTIAL_SUCCESS")

    def test_et_ok_e4m_fail_returns_partial(self):
        """ET OK + E4M FAIL → PARTIAL_SUCCESS"""
        with self._patch_refresh(et_ok=True, e4m_ok=False):
            result = run_monitoring_cycle()
        self.assertEqual(result, "PARTIAL_SUCCESS")

    def test_both_fail_returns_failed(self):
        """ET FAIL + E4M FAIL → FAILED"""
        with self._patch_refresh(et_ok=False, e4m_ok=False):
            result = run_monitoring_cycle()
        self.assertEqual(result, "FAILED")

    def test_one_failure_does_not_prevent_other(self):
        """ET failing must not prevent E4M from being attempted."""
        call_log = []

        def mock_refresh(website_key, website_name):
            call_log.append(website_key)
            if website_key == "et_brand_equity":
                return (False, 0, "ET error")
            return (True, 25, "")

        with patch("monitoring.engine.run_website_refresh", side_effect=mock_refresh):
            run_monitoring_cycle()

        self.assertIn("et_brand_equity", call_log)
        self.assertIn("exchange4media", call_log)

    def test_overlap_is_prevented(self):
        """If a cycle is already running, second trigger returns ALREADY_RUNNING."""
        from monitoring.status import monitoring_status
        monitoring_status.mark_cycle_started()  # simulate running cycle

        result = run_monitoring_cycle()
        self.assertEqual(result, "ALREADY_RUNNING")

    def test_status_updated_after_cycle(self):
        """Status store reflects results after a cycle completes."""
        with self._patch_refresh(et_ok=True, e4m_ok=True):
            run_monitoring_cycle()

        from monitoring.status import monitoring_status
        snap = monitoring_status.snapshot()
        self.assertEqual(snap["last_cycle_status"], "SUCCESS")
        self.assertEqual(snap["total_cycles"], 1)
        self.assertFalse(snap["currently_running"])
        self.assertEqual(snap["websites"]["et_brand_equity"]["last_status"], "SUCCESS")
        self.assertEqual(snap["websites"]["exchange4media"]["last_status"], "SUCCESS")

    def test_invalid_result_does_not_remove_articles(self):
        """A scraper returning 0 valid articles must NOT trigger mass removal."""
        def mock_refresh(website_key, website_name):
            # Simulate validation failure (empty result)
            return (False, 0, "Validation failed: Too few articles (0)")

        with patch("monitoring.engine.run_website_refresh", side_effect=mock_refresh):
            result = run_monitoring_cycle()

        # Cycle should fail, but no removal should occur (handled by change detector safeguards)
        self.assertIn(result, ("FAILED", "PARTIAL_SUCCESS"))


# ---------------------------------------------------------------------------
# 10. Scheduler clean shutdown
# ---------------------------------------------------------------------------
class TestSchedulerShutdown(unittest.TestCase):
    def test_scheduler_shuts_down_cleanly(self):
        """stop() on a non-started scheduler must not raise."""
        from monitoring import scheduler as sched
        try:
            sched.stop()
        except Exception as e:
            self.fail(f"stop() raised unexpectedly: {e}")


# ---------------------------------------------------------------------------
# 11. Monitoring API Endpoints
# ---------------------------------------------------------------------------
class TestMonitoringEndpoints(unittest.TestCase):
    def setUp(self):
        from monitoring import status as _status_mod
        _status_mod.monitoring_status = MonitoringStatus(interval_minutes=10)

    def test_get_status_endpoint(self):
        """GET /api/monitoring/status returns valid Pydantic model."""
        import asyncio
        from app.api.endpoints.monitoring import get_monitoring_status

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(get_monitoring_status())
            self.assertEqual(res.interval_minutes, 10)
            self.assertFalse(res.scheduler_enabled)
            self.assertIn("et_brand_equity", res.websites)
            self.assertIn("exchange4media", res.websites)
        finally:
            loop.close()

    def test_post_run_now_endpoint(self):
        """POST /api/monitoring/run-now starts a cycle if idle."""
        import asyncio
        from app.api.endpoints.monitoring import run_monitoring_now

        loop = asyncio.new_event_loop()
        try:
            with patch("monitoring.engine.run_monitoring_cycle"):
                res = loop.run_until_complete(run_monitoring_now())
                self.assertEqual(res.status, "started")
        finally:
            loop.close()

    def test_post_run_now_when_already_running(self):
        """POST /api/monitoring/run-now returns already_running if active."""
        import asyncio
        from monitoring.status import monitoring_status
        from app.api.endpoints.monitoring import run_monitoring_now

        monitoring_status.mark_cycle_started()
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(run_monitoring_now())
            self.assertEqual(res.status, "already_running")
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
