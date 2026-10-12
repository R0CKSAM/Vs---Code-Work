"""
pipeline.py – Central Pipeline Orchestrator for FanCode Monitoring Engine (Phase 10).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser, sync_playwright
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.validation import assert_valid_settings
from app.database.connection import get_session, init_db, utc_now
from app.database.models import Match, Sport, Tour, Video
from app.database.repositories import ScrapeRunsRepository
from app.maintenance.stale_runs import reclaim_stale_runs
from app.monitor.exceptions import ErrorCategory, FatalPipelineError, classify_error
from app.monitor.models import (
    PipelineRunResult,
    PipelineStatus,
    StageName,
    StageResult,
    StageStatus,
)
from app.monitor.stages import (
    BaseStage,
    ChangeDetectionStage,
    DiscoveryStage,
    LiveNowStage,
    MatchDetailStage,
    NotificationStage,
    PipelineContext,
    ScheduleStage,
    SportsToursStage,
    VideosStage,
)
from app.observability import correlation_scope, heartbeat, metrics

logger = logging.getLogger(__name__)


def _is_in_async_loop() -> bool:
    """Check if an asyncio event loop is actively running on current thread."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class MonitorPipeline:
    """
    Coordinates browser lifecycle, stage execution order, failure isolation,
    bounded retries, and run auditing.
    """

    def __init__(
        self,
        session: Optional[Session] = None,
        stages: Optional[List[BaseStage]] = None,
        browser: Optional[Browser] = None,
        max_retries: Optional[int] = None,
        retry_delay_seconds: Optional[float] = None,
    ) -> None:
        self._session_override = session
        self._browser_override = browser
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "MONITOR_MAX_RETRIES", 1)
        self.retry_delay_seconds = (
            retry_delay_seconds if retry_delay_seconds is not None else getattr(settings, "MONITOR_RETRY_DELAY_SECONDS", 2.0)
        )
        self.stages = stages or self._default_stages()

    # -------------------------------------------------------------------------
    # Public Execution API
    # -------------------------------------------------------------------------

    def execute(
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
        Executes the configured monitoring pipeline end-to-end.
        """
        run_res = PipelineRunResult(
            trigger_type=trigger_type,
            status=PipelineStatus.RUNNING,
            is_dry_run=dry_run,
            started_at=datetime.now(timezone.utc),
        )
        start_t = time.time()
        effective_browser = browser or self._browser_override

        init_db()

        # Resolve session
        if self._session_override:
            return self._execute_with_session(
                session=self._session_override,
                run_res=run_res,
                start_t=start_t,
                dry_run=dry_run,
                skip_discovery=skip_discovery,
                skip_notifications=skip_notifications,
                stage_filter=stage_filter,
                headed=headed,
                browser=effective_browser,
            )
        else:
            with get_session() as session:
                return self._execute_with_session(
                    session=session,
                    run_res=run_res,
                    start_t=start_t,
                    dry_run=dry_run,
                    skip_discovery=skip_discovery,
                    skip_notifications=skip_notifications,
                    stage_filter=stage_filter,
                    headed=headed,
                    browser=effective_browser,
                )

    # -------------------------------------------------------------------------
    # Internal Execution
    # -------------------------------------------------------------------------

    def _execute_with_session(
        self,
        session: Session,
        run_res: PipelineRunResult,
        start_t: float,
        dry_run: bool,
        skip_discovery: bool,
        skip_notifications: bool,
        stage_filter: Optional[str],
        headed: bool,
        browser: Optional[Browser] = None,
    ) -> PipelineRunResult:
        # Validate configuration settings
        assert_valid_settings()

        # Reclaim stale runs safely
        try:
            reclaim_stale_runs(session)
        except Exception as e:
            logger.debug("Stale run check skipped: %s", e)

        runs_repo = ScrapeRunsRepository(session)
        scrape_run = None
        if not dry_run:
            scrape_run = runs_repo.create_run(
                run_type="monitor",
                metadata_json={"trigger_type": run_res.trigger_type},
            )
            session.commit()
            run_res.run_id = scrape_run.id

        run_identifier = str(scrape_run.id if scrape_run else "dry_run")
        heartbeat.touch(stage="pipeline_start", run_id=run_identifier)
        metrics.inc("monitor_cycles_total")

        context = PipelineContext(
            session=session,
            scrape_run_id=scrape_run.id if scrape_run else None,
            is_dry_run=dry_run,
            baseline_data={
                "MATCH": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in session.query(Match).all()
                ],
                "SPORT": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in session.query(Sport).all()
                ],
                "TOUR": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in session.query(Tour).all()
                ],
                "VIDEO": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in session.query(Video).all()
                ],
            },
        )
        session.commit()


        active_stages = self._filter_stages(
            skip_discovery=skip_discovery,
            skip_notifications=skip_notifications,
            stage_filter=stage_filter,
        )

        # Check if browser is needed
        needs_browser = any(getattr(s, "requires_browser", False) for s in active_stages)

        try:
            with correlation_scope(run_id=run_identifier, scrape_run_id=scrape_run.id if scrape_run else None):
                if browser is not None:
                    context.browser = browser
                    self._run_stages_loop(active_stages, context, run_res)
                elif needs_browser:
                    def _run_with_managed_browser():
                        with sync_playwright() as pw:
                            b = pw.chromium.launch(
                                headless=not headed and settings.BROWSER_HEADLESS,
                                args=["--no-sandbox", "--disable-dev-shm-usage"],
                            )
                            try:
                                context.browser = b
                                self._run_stages_loop(active_stages, context, run_res)
                            finally:
                                b.close()
                                context.browser = None

                    if _is_in_async_loop():
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(_run_with_managed_browser)
                            future.result()
                    else:
                        _run_with_managed_browser()
                else:
                    self._run_stages_loop(active_stages, context, run_res)

                # Determine overall pipeline status
                stage_statuses = [r.status for r in run_res.stages.values()]
                if any(s == StageStatus.FAILED for s in stage_statuses):
                    run_res.status = PipelineStatus.PARTIAL if any(s == StageStatus.SUCCESS for s in stage_statuses) else PipelineStatus.FAILED
                else:
                    run_res.status = PipelineStatus.SUCCESS

        except Exception as e:
            cat, act = classify_error(e)
            if cat == ErrorCategory.DATABASE_ERROR:
                metrics.inc("database_errors")
            logger.error("Fatal pipeline error [%s]: %s", cat.value, e, exc_info=True)
            run_res.status = PipelineStatus.FAILED
            run_res.error_summary = str(e)

        finally:
            run_res.completed_at = datetime.now(timezone.utc)
            run_res.duration_seconds = time.time() - start_t

            metrics.set_gauge("last_cycle_duration_seconds", run_res.duration_seconds)
            if run_res.status == PipelineStatus.SUCCESS:
                metrics.inc("monitor_cycles_success")
            elif run_res.status == PipelineStatus.FAILED:
                metrics.inc("monitor_cycles_failed")
            heartbeat.touch(stage="idle", run_id=run_identifier)

            # Audit record completion in database
            if scrape_run and not dry_run:
                total_processed = sum(r.records_processed for r in run_res.stages.values())
                total_created = sum(r.records_created for r in run_res.stages.values())
                total_updated = sum(r.records_updated for r in run_res.stages.values())
                total_changes = sum(r.changes_detected for r in run_res.stages.values())
                total_errors = sum(len(r.errors) for r in run_res.stages.values())

                runs_repo.finish_run(
                    run_id=scrape_run.id,
                    status="success" if run_res.status == PipelineStatus.SUCCESS else "failed",
                    records_processed=total_processed,
                    records_created=total_created,
                    records_updated=total_updated,
                    changes_detected=total_changes,
                    errors_count=total_errors,
                    error_message=run_res.error_summary,
                )
                session.commit()

        logger.info(
            "Pipeline completed [%s] in %.2fs (Run ID: %s)",
            run_res.status.value,
            run_res.duration_seconds,
            run_res.run_id,
        )
        return run_res

    def _run_stages_loop(
        self,
        stages: List[BaseStage],
        context: PipelineContext,
        run_res: PipelineRunResult,
    ) -> None:
        """Executes each stage with failure isolation and bounded retries."""
        for stage in stages:
            stage_res = self._execute_stage_with_retries(stage, context)
            run_res.stages[stage.name] = stage_res

            # Fatal stage failure aborts subsequent stages
            if stage.is_fatal and stage_res.status == StageStatus.FAILED:
                logger.error("Fatal stage [%s] failed. Halting pipeline.", stage.name)
                raise FatalPipelineError(f"Fatal stage [{stage.name}] failed: {stage_res.errors}")

    def _execute_stage_with_retries(self, stage: BaseStage, context: PipelineContext) -> StageResult:
        """Executes a single stage, retrying up to max_retries upon failure."""
        attempts = 0
        last_res = None

        while attempts <= self.max_retries:
            attempts += 1
            last_res = stage.execute(context)
            last_res.retries_attempted = attempts - 1

            if last_res.status == StageStatus.SUCCESS or last_res.status == StageStatus.SKIPPED:
                return last_res

            if attempts <= self.max_retries:
                logger.warning(
                    "Stage [%s] failed (attempt %d/%d). Retrying in %.1fs...",
                    stage.name,
                    attempts,
                    self.max_retries + 1,
                    self.retry_delay_seconds,
                )
                time.sleep(self.retry_delay_seconds)

        return last_res or StageResult(name=stage.name, status=StageStatus.FAILED)

    def _default_stages(self) -> List[BaseStage]:
        """Defines the standard production pipeline sequence."""
        return [
            ScheduleStage(),
            SportsToursStage(),
            MatchDetailStage(),
            LiveNowStage(),
            VideosStage(),
            ChangeDetectionStage(),
            NotificationStage(),
        ]

    def _filter_stages(
        self,
        skip_discovery: bool,
        skip_notifications: bool,
        stage_filter: Optional[str],
    ) -> List[BaseStage]:
        """Filters configured stages based on CLI / run flags."""
        active: List[BaseStage] = []
        for s in self.stages:
            if stage_filter and s.name != stage_filter.lower():
                continue
            if s.name == StageName.DISCOVERY.value and skip_discovery:
                continue
            if s.name == StageName.NOTIFICATIONS.value and skip_notifications:
                continue
            active.append(s)
        return active
