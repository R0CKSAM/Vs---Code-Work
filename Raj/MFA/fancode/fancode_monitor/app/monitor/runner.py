"""
runner.py – Monitor execution controller supporting One-Shot and Continuous Scheduling (Phase 10).
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Browser

from app.config.settings import settings
from app.monitor.lock import MonitorLock
from app.monitor.models import PipelineRunResult, PipelineStatus
from app.monitor.pipeline import MonitorPipeline
from app.observability import heartbeat, metrics

logger = logging.getLogger(__name__)


def sleep_with_countdown(seconds: int, stop_checker: Optional[Callable[[], bool]] = None) -> None:
    """
    Sleeps for the specified number of seconds while displaying an in-place live countdown on stdout.
    Checks stop_checker() every second to support responsive graceful shutdown without altering timing.
    """
    if seconds <= 0:
        return

    # Carriage-return animation is useful at a terminal but turns into one noisy
    # line per second when stdout is redirected to a log collector or file.
    # In that case, sleep responsively without writing transient UI output.
    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if not is_tty:
        for _ in range(seconds):
            if stop_checker and stop_checker():
                break
            time.sleep(1)
        return

    width = max(3, len(str(seconds)))

    for remaining in range(seconds, 0, -1):
        if stop_checker and stop_checker():
            break
        sys.stdout.write(f"\rNext cycle in: {remaining:0{width}d}s")
        sys.stdout.flush()
        time.sleep(1)

    if not (stop_checker and stop_checker()):
        sys.stdout.write(f"\rNext cycle in: {0:0{width}d}s\n")
        sys.stdout.flush()
    else:
        sys.stdout.write("\n")
        sys.stdout.flush()


class MonitorRunner:
    """
    Manages one-shot execution and continuous scheduling with lock enforcement,
    controlled polling intervals, and graceful shutdown handling.
    """

    def __init__(
        self,
        pipeline: Optional[MonitorPipeline] = None,
        lock: Optional[MonitorLock] = None,
        browser: Optional[Browser] = None,
    ) -> None:
        self.pipeline = pipeline or MonitorPipeline(browser=browser)
        self.lock = lock or MonitorLock()
        self.browser = browser
        self._stop_requested = False
        self._setup_signals()

    def run_once(
        self,
        trigger_type: str = "manual",
        dry_run: bool = False,
        skip_discovery: bool = True,
        skip_notifications: bool = False,
        stage_filter: Optional[str] = None,
        headed: bool = False,
        browser: Optional[Browser] = None,
    ) -> PipelineRunResult:
        """
        Executes exactly one pipeline run with exclusive locking.
        """
        effective_browser = browser or self.browser
        if getattr(settings, "MONITOR_LOCK_ENABLED", True):
            if not self.lock.acquire(blocking=False):
                logger.warning("Monitor execution skipped: active lock already held.")
                metrics.inc("lock_failures")
                return PipelineRunResult(
                    trigger_type=trigger_type,
                    status=PipelineStatus.SKIPPED,
                    error_summary="Active lock held by another process",
                    is_dry_run=dry_run,
                )

        try:
            return self.pipeline.execute(
                trigger_type=trigger_type,
                dry_run=dry_run,
                skip_discovery=skip_discovery,
                skip_notifications=skip_notifications,
                stage_filter=stage_filter,
                headed=headed,
                browser=effective_browser,
            )
        finally:
            if getattr(settings, "MONITOR_LOCK_ENABLED", True):
                self.lock.release()

    def run_loop(
        self,
        interval_seconds: Optional[int] = None,
        max_cycles: Optional[int] = None,
        dry_run: bool = False,
        skip_discovery: bool = True,
        skip_notifications: bool = False,
        stage_filter: Optional[str] = None,
        headed: bool = False,
        browser: Optional[Browser] = None,
    ) -> List[PipelineRunResult]:
        """
        Runs the monitor pipeline continuously at the configured interval until interrupted.
        """
        interval = interval_seconds or getattr(settings, "MONITOR_INTERVAL_SECONDS", 300)
        cycles = 0
        results: List[PipelineRunResult] = []

        logger.info("Starting FanCode Monitor Continuous Loop (Interval: %ds, Dry-Run: %s)...", interval, dry_run)
        print(f"FanCode Continuous Monitor active. Polling every {interval}s. Press Ctrl+C to stop.\n")

        try:
            # A loop invocation always performs its initial cycle. A stop request
            # observed during that cycle prevents subsequent cycles and sleeping.
            while cycles == 0 or not self._stop_requested:
                cycles += 1
                logger.info("=== Starting Monitor Cycle #%d ===", cycles)

                res = self.run_once(
                    trigger_type="scheduled",
                    dry_run=dry_run,
                    skip_discovery=skip_discovery,
                    skip_notifications=skip_notifications,
                    stage_filter=stage_filter,
                    headed=headed,
                    browser=browser,
                )
                results.append(res)

                if max_cycles and cycles >= max_cycles:
                    logger.info("Reached maximum requested cycles (%d). Stopping loop.", max_cycles)
                    break

                if self._stop_requested:
                    break

                # Controlled non-busy sleep with in-place live countdown
                logger.info("Cycle #%d complete. Sleeping for %ds...", cycles, interval)
                sleep_with_countdown(interval, stop_checker=lambda: self._stop_requested)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Shutting down gracefully...")
        finally:
            if getattr(settings, "MONITOR_LOCK_ENABLED", True):
                self.lock.release()
            logger.info("Monitor continuous loop terminated cleanly after %d cycles.", cycles)

        return results

    def _setup_signals(self) -> None:
        """Installs signal handlers for graceful shutdown."""
        def _handle_signal(sig, frame):
            logger.info("Shutdown signal received (%s). Requesting pipeline stop...", sig)
            self._stop_requested = True

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            # Signal handling might not be supported in non-main threads
            pass
