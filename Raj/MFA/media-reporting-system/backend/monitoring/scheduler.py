"""
Media Reporting System - Phase 5 APScheduler Integration
Manages the BackgroundScheduler lifecycle and registers the monitoring job.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("monitor")

# Module-level scheduler instance — None until start() is called
_scheduler = None
_JOB_ID = "monitoring_cycle"


def _build_scheduler():
    """
    Creates and returns a configured scheduler.
    Uses APScheduler BackgroundScheduler if available, or falls back to
    a lightweight standard-library threading scheduler with identical interface.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor

        executors = {
            "default": ThreadPoolExecutor(max_workers=1),
        }
        job_defaults = {
            "coalesce": True,        # collapse missed runs into a single execution
            "max_instances": 1,      # hard guarantee: no concurrent cycles
            "misfire_grace_time": 60,  # allow up to 60s late start before skipping
        }
        return BackgroundScheduler(executors=executors, job_defaults=job_defaults)
    except ImportError:
        logger.info("[MONITOR] APScheduler not installed; using built-in ThreadingScheduler fallback")
        return _SimpleThreadingScheduler()


class _SimpleJob:
    def __init__(self, func, interval_seconds, job_id):
        self.func = func
        self.interval_seconds = interval_seconds
        self.id = job_id
        self.next_run_time = None


class _SimpleThreadingScheduler:
    """Lightweight pure-Python fallback scheduler with APScheduler-compatible API."""

    def __init__(self, *args, **kwargs):
        import threading
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._jobs = {}
        self.running = False

    def add_job(self, func, trigger="interval", minutes=10, id="job", replace_existing=True, **kwargs):
        from datetime import datetime, timezone, timedelta
        interval_secs = minutes * 60
        job = _SimpleJob(func, interval_secs, id)
        job.next_run_time = datetime.now(timezone.utc) + timedelta(seconds=interval_secs)
        with self._lock:
            self._jobs[id] = job
        return job

    def get_job(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def start(self):
        import threading
        from datetime import datetime, timezone, timedelta
        if self.running:
            return
        self.running = True
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                with self._lock:
                    jobs = list(self._jobs.values())
                for job in jobs:
                    # Wait for interval
                    if self._stop_event.wait(timeout=job.interval_seconds):
                        break
                    if not self._stop_event.is_set():
                        try:
                            job.func()
                        except Exception as e:
                            logger.exception("[MONITOR] Job execution error: %s", e)
                        job.next_run_time = datetime.now(timezone.utc) + timedelta(seconds=job.interval_seconds)

        self._thread = threading.Thread(target=_loop, name="monitor-scheduler-fallback", daemon=True)
        self._thread.start()

    def shutdown(self, wait=False):
        self.running = False
        self._stop_event.set()
        if wait and self._thread:
            self._thread.join(timeout=5)



def start(run_initial_cycle: bool = True) -> None:
    """
    Starts the APScheduler BackgroundScheduler and registers the monitoring job.
    Idempotent: safe to call multiple times (e.g. uvicorn --reload).
    """
    global _scheduler
    from monitoring.engine import run_monitoring_cycle, get_interval_minutes
    from monitoring.status import monitoring_status

    interval = get_interval_minutes()

    # Guard against duplicate starts (uvicorn reload executes startup twice)
    if _scheduler is not None and _scheduler.running:
        logger.info("[MONITOR] Scheduler already running — skipping duplicate start")
        return

    _scheduler = _build_scheduler()
    _scheduler.add_job(
        func=run_monitoring_cycle,
        trigger="interval",
        minutes=interval,
        id=_JOB_ID,
        replace_existing=True,
    )
    _scheduler.start()
    monitoring_status.mark_scheduler_started(interval)

    # Update next_run_at from the scheduler's job
    _update_next_run()

    logger.info(
        "[MONITOR] Scheduler started — interval: %d minutes, initial cycle: %s",
        interval,
        run_initial_cycle,
    )

    if run_initial_cycle:
        # Run the first cycle synchronously in a daemon thread so it doesn't
        # block FastAPI startup but completes before requests are served.
        import threading
        t = threading.Thread(target=run_monitoring_cycle, name="monitor-initial", daemon=True)
        t.start()


def stop() -> None:
    """Gracefully stops the scheduler. Safe to call even if not started."""
    global _scheduler
    from monitoring.status import monitoring_status

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[MONITOR] Scheduler stopped cleanly")
    else:
        logger.info("[MONITOR] Scheduler was not running — nothing to stop")

    monitoring_status.mark_scheduler_stopped()
    _scheduler = None


def _update_next_run() -> None:
    """Reads next scheduled run time from APScheduler and persists it in status."""
    global _scheduler
    from monitoring.status import monitoring_status

    if _scheduler is None:
        return
    job = _scheduler.get_job(_JOB_ID)
    if job and job.next_run_time:
        monitoring_status.set_next_run_at(job.next_run_time)


def is_running() -> bool:
    global _scheduler
    return _scheduler is not None and _scheduler.running
