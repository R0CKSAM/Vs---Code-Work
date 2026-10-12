"""
test_observability_metrics.py – Unit tests for lightweight operational metrics tracking (Phase 11).
"""

from __future__ import annotations

import threading
from app.observability.metrics import MetricsRegistry


class TestMetricsRegistry:
    def test_counter_increments(self):
        reg = MetricsRegistry()
        reg.inc("monitor_cycles_total", 1)
        reg.inc("monitor_cycles_total", 2)
        reg.inc("records_processed", 50)

        assert reg.get("monitor_cycles_total") == 3
        assert reg.get("records_processed") == 50
        assert reg.get("non_existent_key") == 0

    def test_gauge_setting(self):
        reg = MetricsRegistry()
        reg.set_gauge("last_cycle_duration_seconds", 12.34)
        snapshot = reg.snapshot()

        assert snapshot["last_cycle_duration_seconds"] == 12.34

    def test_reset_behavior(self):
        reg = MetricsRegistry()
        reg.inc("monitor_cycles_success", 5)
        reg.inc("database_errors", 2)
        reg.reset()

        assert reg.get("monitor_cycles_success") == 0
        assert reg.get("database_errors") == 0

    def test_thread_safety(self):
        reg = MetricsRegistry()
        num_threads = 10
        increments_per_thread = 100

        def worker():
            for _ in range(increments_per_thread):
                reg.inc("stage_runs_total", 1)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert reg.get("stage_runs_total") == num_threads * increments_per_thread
