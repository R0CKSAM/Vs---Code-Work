"""
stages.py – Pipeline Stage abstractions and concrete implementations for FanCode Monitor (Phase 10).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from app.change_detection.detector import ChangeDetector
from app.config.settings import settings
from app.monitor.models import StageName, StageResult, StageStatus
from app.notifications.service import NotificationService
from app.scraper.discovery.crawler import FanCodeCrawler, persist_discovery_to_db
from app.scraper.live_now.scraper import FanCodeLiveNowScraper
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper
from app.scraper.schedule.scraper import FanCodeScheduleScraper
from app.scraper.sports.scraper import FanCodeSportsScraper
from app.scraper.tours.scraper import FanCodeToursScraper
from app.scraper.videos.scraper import FanCodeVideosScraper

logger = logging.getLogger(__name__)


from app.observability import correlation_scope, heartbeat, metrics


@dataclass
class PipelineContext:
    """Shared execution context passed across pipeline stages."""
    session: Session
    browser: Optional[Browser] = None
    scrape_run_id: Optional[int] = None
    is_dry_run: bool = False
    scraped_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)


class BaseStage(ABC):
    """Abstract base class for all pipeline stages."""

    name: str = "base"
    is_fatal: bool = False
    requires_browser: bool = False

    @abstractmethod
    def run(self, context: PipelineContext) -> StageResult:
        """Executes stage logic and returns detailed StageResult."""
        pass

    def execute(self, context: PipelineContext) -> StageResult:
        """Wraps run execution with timing, error capture, and logging."""
        with correlation_scope(stage=self.name, scrape_run_id=context.scrape_run_id):
            heartbeat.touch(stage=self.name)
            metrics.inc("stage_runs_total")

            result = StageResult(name=self.name, status=StageStatus.RUNNING)
            result.started_at = datetime.now(timezone.utc)
            start_t = time.time()

            logger.info("Starting stage [%s] (dry_run=%s)...", self.name, context.is_dry_run)
            try:
                res = self.run(context)
                res.started_at = result.started_at
                res.completed_at = datetime.now(timezone.utc)
                res.duration_seconds = time.time() - start_t
                if res.status in (StageStatus.RUNNING, StageStatus.PENDING):
                    res.status = StageStatus.SUCCESS

                if res.status == StageStatus.SUCCESS:
                    metrics.inc("stage_runs_success")
                elif res.status == StageStatus.FAILED:
                    metrics.inc("stage_runs_failed")

                metrics.inc("records_processed", res.records_processed)
                metrics.inc("records_created", res.records_created)
                metrics.inc("records_updated", res.records_updated)
                metrics.inc("change_events_created", res.changes_detected)
                metrics.inc("notifications_sent", res.notifications_sent)

                logger.info("Stage [%s] finished with status %s in %.2fs", self.name, res.status.value, res.duration_seconds)
                return res
            except Exception as e:
                metrics.inc("stage_runs_failed")
                result.completed_at = datetime.now(timezone.utc)
                result.duration_seconds = time.time() - start_t
                result.status = StageStatus.FAILED
                result.errors.append(str(e))
                logger.error("Stage [%s] failed after %.2fs: %s", self.name, result.duration_seconds, e, exc_info=True)
                return result


# -----------------------------------------------------------------------------
# Concrete Scraper Stages
# -----------------------------------------------------------------------------

class ScheduleStage(BaseStage):
    """Scrapes upcoming & scheduled match fixtures."""
    name = StageName.SCHEDULE.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            result.warnings.append("Browser instance not available")
            return result

        scraper = FanCodeScheduleScraper(browser=context.browser)
        matches = scraper.scrape(persist_db=not context.is_dry_run)
        result.records_processed = len(matches)

        context.scraped_data["matches"] = [
            m.to_dict() if hasattr(m, "to_dict") else {
                "external_id": getattr(m, "external_id", None),
                "title": getattr(m, "title", ""),
                "status": getattr(m, "status", "UNKNOWN"),
                "venue": getattr(m, "venue", None),
                "start_time": getattr(m, "start_time", None),
                "team_a_name": getattr(m, "team_a_name", None),
                "team_b_name": getattr(m, "team_b_name", None),
                "source_url": getattr(m, "source_url", ""),
                "score_summary": getattr(m, "score_summary", None),
            }
            for m in matches
        ]
        result.status = StageStatus.SUCCESS
        return result


class SportsToursStage(BaseStage):
    """Scrapes sports categories and tournaments/series."""
    name = StageName.SPORTS.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            return result

        sports_scraper = FanCodeSportsScraper(browser=context.browser)
        sports = sports_scraper.scrape(persist_db=not context.is_dry_run)

        tours_scraper = FanCodeToursScraper(browser=context.browser)
        tours = tours_scraper.scrape(persist_db=not context.is_dry_run)

        result.records_processed = len(sports) + len(tours)
        context.scraped_data["sports"] = [
            {"slug": s.slug, "external_id": s.external_id, "name": s.name, "source_url": s.source_url}
            for s in sports
        ]
        context.scraped_data["tours"] = [
            {"slug": t.slug, "external_id": t.external_id, "name": t.name, "source_url": t.source_url}
            for t in tours
        ]
        result.status = StageStatus.SUCCESS
        return result


class MatchDetailStage(BaseStage):
    """Enriches match details (venues, lineups, detailed timestamps)."""
    name = StageName.MATCH_DETAIL.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            return result

        scraper = FanCodeMatchDetailScraper(browser=context.browser)
        enriched = scraper.enrich_batch(
            limit=getattr(settings, "MATCH_DETAIL_MAX_ITEMS", 20),
            persist_db=not context.is_dry_run,
        )
        result.records_processed = len(enriched)
        result.status = StageStatus.SUCCESS
        return result


class LiveNowStage(BaseStage):
    """Scrapes active in-progress live fixtures."""
    name = StageName.LIVE_NOW.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            return result

        scraper = FanCodeLiveNowScraper(browser=context.browser)
        live_matches = scraper.scrape(persist_db=not context.is_dry_run)
        result.records_processed = len(live_matches)

        raw_live = [
            {
                "external_id": getattr(m, "match_external_id", None) or getattr(m, "external_id", None),
                "title": getattr(m, "title", "") or getattr(m, "match_title", ""),
                "status": getattr(m, "status", "LIVE"),
                "venue": getattr(m, "venue", None),
                "score_summary": getattr(m, "score_summary", None),
                "source_url": getattr(m, "source_url", ""),
                "team_a_name": getattr(m, "team_a_name", None),
                "team_b_name": getattr(m, "team_b_name", None),
            }
            for m in live_matches
        ]
        # Merge or append to context matches
        existing = context.scraped_data.get("matches", [])
        context.scraped_data["matches"] = existing + raw_live
        result.status = StageStatus.SUCCESS
        return result


class VideosStage(BaseStage):
    """Scrapes match highlights, clips, and video replays."""
    name = StageName.VIDEOS.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            return result

        scraper = FanCodeVideosScraper(browser=context.browser)
        videos = scraper.scrape(persist_db=not context.is_dry_run)
        result.records_processed = len(videos)

        context.scraped_data["videos"] = [
            {
                "slug": v.slug,
                "external_id": v.external_id,
                "title": v.title,
                "video_type": v.video_type,
                "duration_seconds": v.duration_seconds,
                "source_url": v.source_url,
            }
            for v in videos
        ]
        result.status = StageStatus.SUCCESS
        return result


# -----------------------------------------------------------------------------
# Change Detection & Notification Stages
# -----------------------------------------------------------------------------

class ChangeDetectionStage(BaseStage):
    """Executes state comparison against database and generates change_events."""
    name = StageName.CHANGE_DETECTION.value
    is_fatal = False

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        detector = ChangeDetector(session=context.session)

        matches_data = context.scraped_data.get("matches")
        sports_data = context.scraped_data.get("sports")
        tours_data = context.scraped_data.get("tours")
        videos_data = context.scraped_data.get("videos")

        det_res = detector.detect_all(
            matches_data=matches_data,
            sports_data=sports_data,
            tours_data=tours_data,
            videos_data=videos_data,
            scrape_run_id=context.scrape_run_id,
            dry_run=context.is_dry_run,
        )

        result.records_processed = det_res.entities_checked
        result.records_created = det_res.created_events
        result.records_updated = det_res.updated_events
        result.changes_detected = len(det_res.events)
        result.status = StageStatus.SUCCESS
        return result


class NotificationStage(BaseStage):
    """Consumes unnotified change events, groups digests, renders and delivers alerts."""
    name = StageName.NOTIFICATIONS.value
    is_fatal = False

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not getattr(settings, "MONITOR_NOTIFICATION_ENABLED", True):
            result.status = StageStatus.SKIPPED
            result.warnings.append("Notifications disabled in settings")
            return result

        service = NotificationService(session=context.session)
        notif_res = service.run(
            scrape_run_id=context.scrape_run_id,
            dry_run=context.is_dry_run,
        )

        result.records_processed = notif_res.events_inspected
        result.notifications_sent = notif_res.emails_sent
        result.metadata["batches_created"] = notif_res.batches_created
        result.metadata["deliveries_failed"] = notif_res.deliveries_failed

        if notif_res.errors:
            result.status = StageStatus.PARTIAL
            result.errors.extend(notif_res.errors)
        else:
            result.status = StageStatus.SUCCESS

        return result


class DiscoveryStage(BaseStage):
    """Optional crawl for discovering new FanCode links."""
    name = StageName.DISCOVERY.value
    is_fatal = False
    requires_browser = True

    def run(self, context: PipelineContext) -> StageResult:
        result = StageResult(name=self.name)
        if not context.browser:
            result.status = StageStatus.SKIPPED
            return result

        crawler = FanCodeCrawler(browser=context.browser)
        res = crawler.run()
        if not context.is_dry_run:
            persist_discovery_to_db(res)
        result.records_processed = len(res.pages)
        result.status = StageStatus.SUCCESS
        return result
