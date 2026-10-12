"""
metrics.py – Lightweight In-Process Operational Metrics for FanCode Monitor (Phase 11).

Tracks counters and metrics across monitor cycles, stages, data volumes, alerts,
and error events without requiring heavy external dependencies.
"""

from __future__ import annotations

import threading
from typing import Any, Dict


class MetricsRegistry:
    """Thread-safe in-process metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self.reset()

    def reset(self) -> None:
        """Resets all metrics to baseline zero."""
        with self._lock:
            self._counters = {
                "monitor_cycles_total": 0,
                "monitor_cycles_success": 0,
                "monitor_cycles_failed": 0,
                "stage_runs_total": 0,
                "stage_runs_success": 0,
                "stage_runs_failed": 0,
                "stage_retries_total": 0,
                "records_processed": 0,
                "records_created": 0,
                "records_updated": 0,
                "change_events_created": 0,
                "notifications_created": 0,
                "notifications_sent": 0,
                "notifications_failed": 0,
                "database_errors": 0,
                "lock_failures": 0,
            }
            self._gauges = {
                "last_cycle_duration_seconds": 0.0,
            }

    def inc(self, key: str, value: int = 1) -> None:
        """Increments a counter."""
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def set_gauge(self, key: str, value: float) -> None:
        """Sets a gauge value."""
        with self._lock:
            self._gauges[key] = float(value)

    def get(self, key: str, default: int = 0) -> int:
        """Retrieves a counter value."""
        with self._lock:
            return self._counters.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """Returns a snapshot dictionary of all metrics."""
        with self._lock:
            res: Dict[str, Any] = dict(self._counters)
            res.update(self._gauges)
            return res


# Global singleton instance
metrics = MetricsRegistry()
