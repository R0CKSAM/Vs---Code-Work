"""
repositories.py – Data access and repository patterns for FanCode entities.

Implements clean, transactional methods for:
- SportsRepository
- ToursRepository
- MatchesRepository
- VideosRepository
- PagesRepository
- ChangeEventsRepository
- ScrapeRunsRepository

All repositories use modern SQLAlchemy 2.x select() statements and handle upserts deterministically.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.connection import utc_now
from app.database.models import (
    ChangeEvent,
    Match,
    Page,
    ScrapeRun,
    Sport,
    Tour,
    Video,
)
from app.scraper.discovery.url_normalizer import normalize

logger = logging.getLogger(__name__)


class SportsRepository:
    """Repository for Sport entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Sport:
        now = utc_now()
        kwargs.setdefault("first_seen_at", now)
        kwargs.setdefault("last_seen_at", now)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        sport = Sport(**kwargs)
        self.session.add(sport)
        self.session.flush()
        return sport

    def get_by_id(self, sport_id: int) -> Optional[Sport]:
        return self.session.get(Sport, sport_id)

    def get_by_external_id(self, external_id: str) -> Optional[Sport]:
        if not external_id:
            return None
        stmt = select(Sport).where(Sport.external_id == str(external_id))
        return self.session.scalars(stmt).first()

    def get_by_slug(self, slug: str) -> Optional[Sport]:
        stmt = select(Sport).where(Sport.slug == slug)
        return self.session.scalars(stmt).first()

    def get_by_source_url(self, source_url: str) -> Optional[Sport]:
        stmt = select(Sport).where(Sport.source_url == source_url)
        return self.session.scalars(stmt).first()

    def upsert(self, **kwargs) -> Sport:
        """
        Upsert sport: looks up by external_id if present, else by slug or source_url.
        Updates fields, last_seen_at, and updated_at.
        """
        now = utc_now()
        external_id = kwargs.get("external_id")
        slug = kwargs.get("slug")
        source_url = kwargs.get("source_url")

        sport: Optional[Sport] = None
        if external_id:
            sport = self.get_by_external_id(external_id)
        if not sport and slug:
            sport = self.get_by_slug(slug)
        if not sport and source_url:
            sport = self.get_by_source_url(source_url)

        if sport:
            for k, v in kwargs.items():
                if v is not None and k not in ("id", "first_seen_at", "created_at"):
                    setattr(sport, k, v)
            sport.last_seen_at = now
            sport.updated_at = now
            self.session.flush()
            return sport
        return self.create(**kwargs)


class ToursRepository:
    """Repository for Tour entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Tour:
        now = utc_now()
        kwargs.setdefault("first_seen_at", now)
        kwargs.setdefault("last_seen_at", now)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        tour = Tour(**kwargs)
        self.session.add(tour)
        self.session.flush()
        return tour

    def get_by_id(self, tour_id: int) -> Optional[Tour]:
        return self.session.get(Tour, tour_id)

    def get_by_external_id(self, external_id: str) -> Optional[Tour]:
        if not external_id:
            return None
        stmt = select(Tour).where(Tour.external_id == str(external_id))
        return self.session.scalars(stmt).first()

    def get_by_slug(self, slug: str) -> Optional[Tour]:
        stmt = select(Tour).where(Tour.slug == slug)
        return self.session.scalars(stmt).first()

    def get_by_source_url(self, source_url: str) -> Optional[Tour]:
        stmt = select(Tour).where(Tour.source_url == source_url)
        return self.session.scalars(stmt).first()

    def upsert(self, **kwargs) -> Tour:
        now = utc_now()
        external_id = kwargs.get("external_id")
        slug = kwargs.get("slug")
        source_url = kwargs.get("source_url")

        tour: Optional[Tour] = None
        if external_id:
            tour = self.get_by_external_id(external_id)
        if not tour and slug:
            tour = self.get_by_slug(slug)
        if not tour and source_url:
            tour = self.get_by_source_url(source_url)

        if tour:
            for k, v in kwargs.items():
                if v is not None and k not in ("id", "first_seen_at", "created_at"):
                    setattr(tour, k, v)
            tour.last_seen_at = now
            tour.updated_at = now
            self.session.flush()
            return tour
        return self.create(**kwargs)


GENERIC_MATCH_SLUGS = {
    "match",
    "matches",
    "unnamed-match",
    "fixture",
    "fixtures",
    "game",
    "games",
    "event",
    "events",
    "final",
    "finals",
    "semi-final",
    "semi-finals",
    "quarter-final",
    "quarter-finals",
    "live",
    "schedule",
}


class MatchesRepository:
    """Repository for Match entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Match:
        now = utc_now()
        kwargs.setdefault("first_seen_at", now)
        kwargs.setdefault("last_seen_at", now)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        match = Match(**kwargs)
        self.session.add(match)
        self.session.flush()
        return match

    def get_by_id(self, match_id: int) -> Optional[Match]:
        return self.session.get(Match, match_id)

    def get_by_external_id(self, external_id: Any) -> Optional[Match]:
        from app.scraper.live_now.normalizer import clean_match_external_id
        clean_id = clean_match_external_id(external_id)
        if not clean_id:
            return None
        stmt = select(Match).where(Match.external_id == clean_id)
        return self.session.scalars(stmt).first()

    def get_by_source_url(self, source_url: str) -> Optional[Match]:
        if not source_url or not str(source_url).strip():
            return None
        norm = normalize(source_url)
        if norm:
            stmt = select(Match).where((Match.source_url == source_url) | (Match.source_url == norm))
        else:
            stmt = select(Match).where(Match.source_url == source_url)
        return self.session.scalars(stmt).first()

    def get_by_slug(self, slug: str) -> Optional[Match]:
        if not slug or not str(slug).strip():
            return None
        import re
        clean_slug = str(slug).strip().lower()
        if clean_slug in GENERIC_MATCH_SLUGS or re.match(r"^match(-\d+)?$", clean_slug):
            return None

        stmt = select(Match).where(Match.slug == clean_slug)
        res = self.session.scalars(stmt).first()
        if res:
            return res
        # If slug has trailing ID (e.g. 'bangladesh-vs-zimbabwe-139151'), try base slug 'bangladesh-vs-zimbabwe'
        # Do NOT strip numeric suffix if the slug is generic (e.g. 'match-1' -> 'match')
        base_slug = re.sub(r"-\d+$", "", clean_slug)
        if (
            base_slug
            and base_slug != clean_slug
            and base_slug not in GENERIC_MATCH_SLUGS
            and not re.match(r"^match(-\d+)?$", base_slug)
        ):
            stmt = select(Match).where(Match.slug == base_slug)
            res = self.session.scalars(stmt).first()
            if res:
                return res
        return None

    def upsert(self, **kwargs) -> Match:
        import re
        from app.scraper.live_now.normalizer import clean_match_external_id
        now = utc_now()
        external_id = kwargs.get("external_id")
        source_url = kwargs.get("source_url")
        slug = kwargs.get("slug")

        clean_ext_id = clean_match_external_id(external_id)

        match: Optional[Match] = None
        # Preferred identity order:
        # 1. external_id when present and valid
        if clean_ext_id:
            match = self.get_by_external_id(clean_ext_id)
        # 2. Exact canonical source_url (excluding generic listing URLs)
        if not match and source_url and str(source_url).strip():
            norm_url = normalize(source_url) or source_url
            if norm_url not in (
                "https://www.fancode.com",
                "https://www.fancode.com/",
                "https://www.fancode.com/live",
                "https://www.fancode.com/live-now",
                "https://www.fancode.com/live-now/all-sports",
                "https://www.fancode.com/schedule",
                "https://www.fancode.com/video",
            ):
                match = self.get_by_source_url(source_url)
        # 3. Normalized slug only as a fallback (and only if not a generic slug like match-1, match-2)
        if not match and slug and str(slug).strip():
            clean_slug = str(slug).strip().lower()
            if clean_slug not in GENERIC_MATCH_SLUGS and not re.match(r"^match(-\d+)?$", clean_slug):
                match = self.get_by_slug(slug)

        if match:
            # If incoming has valid external_id and existing does not, backfill it
            if clean_ext_id and not match.external_id:
                match.external_id = clean_ext_id

            for k, v in kwargs.items():
                if v is not None and k not in ("id", "first_seen_at", "created_at"):
                    if k == "external_id":
                        # Invariant 2: Non-null existing external_id must NEVER be overwritten
                        if match.external_id:
                            continue
                        clean_ext = clean_match_external_id(v)
                        if clean_ext:
                            match.external_id = clean_ext
                        continue
                    # For source_url: keep existing specific source_url if incoming is generic
                    if k == "source_url" and match.source_url:
                        if isinstance(v, str) and (
                            v.endswith("/schedule")
                            or v.endswith("/live-now/all-sports")
                            or v.endswith("/live-now")
                            or v.endswith("/live")
                        ):
                            continue
                    setattr(match, k, v)
            match.last_seen_at = now
            match.updated_at = now
            self.session.flush()
            return match
        return self.create(**kwargs)


class VideosRepository:
    """Repository for Video entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Video:
        now = utc_now()
        kwargs.setdefault("first_seen_at", now)
        kwargs.setdefault("last_seen_at", now)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        video = Video(**kwargs)
        self.session.add(video)
        self.session.flush()
        return video

    def get_by_id(self, video_id: int) -> Optional[Video]:
        return self.session.get(Video, video_id)

    def get_by_external_id(self, external_id: str) -> Optional[Video]:
        if not external_id:
            return None
        stmt = select(Video).where(Video.external_id == str(external_id))
        return self.session.scalars(stmt).first()

    def get_by_source_url(self, source_url: str) -> Optional[Video]:
        stmt = select(Video).where(Video.source_url == source_url)
        return self.session.scalars(stmt).first()

    def upsert(self, **kwargs) -> Video:
        now = utc_now()
        external_id = kwargs.get("external_id")
        source_url = kwargs.get("source_url")

        video: Optional[Video] = None
        if external_id:
            video = self.get_by_external_id(external_id)
        if not video and source_url:
            video = self.get_by_source_url(source_url)

        if video:
            for k, v in kwargs.items():
                if v is not None and k not in ("id", "first_seen_at", "created_at"):
                    setattr(video, k, v)
            video.last_seen_at = now
            video.updated_at = now
            self.session.flush()
            return video
        return self.create(**kwargs)


class PagesRepository:
    """Repository for discovered FanCode Page entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Page:
        now = utc_now()
        canonical = kwargs.get("canonical_url") or kwargs.get("url")
        norm_canonical = normalize(canonical) or canonical
        kwargs["canonical_url"] = norm_canonical

        kwargs.setdefault("first_seen_at", now)
        kwargs.setdefault("last_seen_at", now)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)

        page = Page(**kwargs)
        self.session.add(page)
        self.session.flush()
        return page

    def get_by_canonical_url(self, canonical_url: str) -> Optional[Page]:
        norm = normalize(canonical_url) or canonical_url
        stmt = select(Page).where(Page.canonical_url == norm)
        return self.session.scalars(stmt).first()

    def upsert(self, **kwargs) -> Page:
        """
        Upsert a page by its normalized canonical URL.
        Updates metadata, last_seen_at, and updated_at.
        """
        now = utc_now()
        canonical = kwargs.get("canonical_url") or kwargs.get("url")
        norm_canonical = normalize(canonical) or canonical
        kwargs["canonical_url"] = norm_canonical

        page = self.get_by_canonical_url(norm_canonical)
        if page:
            for k, v in kwargs.items():
                if v is not None and k not in ("id", "first_seen_at", "created_at"):
                    setattr(page, k, v)
            page.last_seen_at = now
            page.updated_at = now
            self.session.flush()
            return page
        return self.create(**kwargs)

    def mark_checked(self, canonical_url: str) -> Optional[Page]:
        page = self.get_by_canonical_url(canonical_url)
        if page:
            now = utc_now()
            page.last_checked_at = now
            page.last_seen_at = now
            page.updated_at = now
            self.session.flush()
        return page


class ChangeEventsRepository:
    """Repository for ChangeEvent logs (foundation for Phase 8)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> ChangeEvent:
        now = utc_now()
        kwargs.setdefault("detected_at", now)
        kwargs.setdefault("created_at", now)
        event = ChangeEvent(**kwargs)
        self.session.add(event)
        self.session.flush()
        return event

    def get_recent(self, limit: int = 50) -> List[ChangeEvent]:
        stmt = select(ChangeEvent).order_by(desc(ChangeEvent.detected_at)).limit(limit)
        return list(self.session.scalars(stmt).all())

    def get_unnotified(self, limit: int = 50) -> List[ChangeEvent]:
        stmt = select(ChangeEvent).where(ChangeEvent.notified_at.is_(None)).order_by(ChangeEvent.detected_at).limit(limit)
        return list(self.session.scalars(stmt).all())

    def mark_notified(self, event_id: int) -> Optional[ChangeEvent]:
        event = self.session.get(ChangeEvent, event_id)
        if event:
            event.notified_at = utc_now()
            self.session.flush()
        return event

    def find_existing_event(
        self,
        entity_type: str,
        entity_id: int,
        change_type: str,
        field_name: Optional[str] = None,
        new_value: Optional[str] = None,
    ) -> Optional[ChangeEvent]:
        """Check if an identical change event has already been recorded (deduplication)."""
        stmt = select(ChangeEvent).where(
            ChangeEvent.entity_type == entity_type,
            ChangeEvent.entity_id == entity_id,
            ChangeEvent.change_type == change_type,
        )
        if field_name:
            stmt = stmt.where(ChangeEvent.field_name == field_name)
        if new_value:
            stmt = stmt.where(ChangeEvent.new_value == new_value)
        return self.session.scalars(stmt).first()

    def get_for_entity(self, entity_type: str, entity_id: int) -> List[ChangeEvent]:
        stmt = select(ChangeEvent).where(
            ChangeEvent.entity_type == entity_type,
            ChangeEvent.entity_id == entity_id,
        ).order_by(desc(ChangeEvent.detected_at))
        return list(self.session.scalars(stmt).all())



class ScrapeRunsRepository:
    """Repository for ScrapeRun audits."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, run_type: str = "discovery", metadata_json: Optional[Dict[str, Any]] = None) -> ScrapeRun:
        now = utc_now()
        run = ScrapeRun(
            run_type=run_type,
            started_at=now,
            status="running",
            metadata_json=metadata_json,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run_id: int,
        status: str = "success",
        pages_discovered: int = 0,
        records_processed: int = 0,
        records_created: int = 0,
        records_updated: int = 0,
        changes_detected: int = 0,
        errors_count: int = 0,
        error_message: Optional[str] = None,
    ) -> Optional[ScrapeRun]:
        run = self.session.get(ScrapeRun, run_id)
        if run:
            run.finished_at = utc_now()
            run.status = status
            run.pages_discovered = pages_discovered
            run.records_processed = records_processed
            run.records_created = records_created
            run.records_updated = records_updated
            run.changes_detected = changes_detected
            run.errors_count = errors_count
            run.error_message = error_message
            self.session.flush()
        return run

    def get_latest(self, run_type: Optional[str] = None) -> Optional[ScrapeRun]:
        stmt = select(ScrapeRun)
        if run_type:
            stmt = stmt.where(ScrapeRun.run_type == run_type)
        stmt = stmt.order_by(desc(ScrapeRun.started_at)).limit(1)
        return self.session.scalars(stmt).first()

    def get_recent(self, limit: int = 20) -> List[ScrapeRun]:
        stmt = select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(limit)
        return list(self.session.scalars(stmt).all())
