"""Deterministic cleanup for test fixtures accidentally written to production.

This command deliberately matches complete, reviewed identities. It never uses broad
patterns such as ``LIKE '%test%'`` for deletion.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.database.connection import create_db_engine, get_session
from app.database.models import (
    ChangeEvent,
    Match,
    NotificationBatch,
    NotificationDelivery,
    NotificationEventLink,
    Page,
    ScrapeRun,
    Sport,
    Tour,
    Video,
)


MATCH_IDENTITIES = (
    ("match-901", "https://www.fancode.com/matches/ind-vs-aus-1st-odi"),
    ("match-e2e-501", "https://www.fancode.com/matches/e2e-initial"),
    ("e2e-live-101", "https://www.fancode.com/matches/e2e-pre-live"),
)
VIDEO_IDENTITIES = (
    ("e2e-vid-101", "https://www.fancode.com/video/vid-high-101"),
)
TOUR_IDENTITIES = (
    ("tour-101", "https://www.fancode.com/tours/ipl-2026"),
    ("10", "https://www.fancode.com/tours/indian-premier-league-2026"),
    (None, "https://www.fancode.com/video"),
)
SPORT_RESIDUE = (
    "sport-1",
    "cricket",
)
COUNT_MODELS = {
    "sports": Sport,
    "tours": Tour,
    "matches": Match,
    "videos": Video,
    "pages": Page,
    "scrape_runs": ScrapeRun,
    "change_events": ChangeEvent,
    "notification_batches": NotificationBatch,
    "notification_deliveries": NotificationDelivery,
    "notification_event_links": NotificationEventLink,
}


def _counts(session: Session) -> dict[str, int]:
    return {
        name: session.scalar(select(func.count()).select_from(model)) or 0
        for name, model in COUNT_MODELS.items()
    }


def _find_exact(session: Session, model: type, identities: Iterable[tuple[str | None, str]]) -> list[Any]:
    rows: list[Any] = []
    for external_id, source_url in identities:
        stmt = select(model).where(model.source_url == source_url)
        stmt = stmt.where(model.external_id.is_(None) if external_id is None else model.external_id == external_id)
        row = session.scalars(stmt).first()
        if row is not None:
            rows.append(row)
    return rows


def _row_summary(row: Any) -> dict[str, Any]:
    return {
        key: getattr(row, key, None)
        for key in ("id", "external_id", "title", "name", "slug", "source_url", "status", "created_at", "updated_at")
        if hasattr(row, key)
    }


def cleanup_confirmed_test_data(session: Session, *, dry_run: bool = True) -> dict[str, Any]:
    """Find and optionally remove only the reviewed fixture identities above."""
    before = _counts(session)
    matches = _find_exact(session, Match, MATCH_IDENTITIES)
    videos = _find_exact(session, Video, VIDEO_IDENTITIES)
    tours = _find_exact(session, Tour, TOUR_IDENTITIES)
    sport = session.scalars(
        select(Sport).where(Sport.external_id == SPORT_RESIDUE[0], Sport.slug == SPORT_RESIDUE[1])
    ).first()

    entity_ids = {
        "match": [row.id for row in matches],
        "video": [row.id for row in videos],
        "tour": [row.id for row in tours],
    }
    event_ids: list[int] = []
    for entity_type, ids in entity_ids.items():
        if ids:
            event_ids.extend(
                session.scalars(
                    select(ChangeEvent.id).where(
                        func.lower(ChangeEvent.entity_type) == entity_type,
                        ChangeEvent.entity_id.in_(ids),
                    )
                ).all()
            )

    link_rows = []
    if event_ids:
        link_rows = list(
            session.execute(
                select(NotificationEventLink.id, NotificationEventLink.batch_id).where(
                    NotificationEventLink.change_event_id.in_(event_ids)
                )
            ).all()
        )
    affected_batch_ids = sorted({row.batch_id for row in link_rows})
    exclusive_batch_ids: list[int] = []
    for batch_id in affected_batch_ids:
        all_event_ids = set(
            session.scalars(
                select(NotificationEventLink.change_event_id).where(NotificationEventLink.batch_id == batch_id)
            ).all()
        )
        if all_event_ids and all_event_ids.issubset(set(event_ids)):
            exclusive_batch_ids.append(batch_id)

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "candidates": {
            "matches": [_row_summary(row) for row in matches],
            "videos": [_row_summary(row) for row in videos],
            "tours": [_row_summary(row) for row in tours],
            "sport_fields": [_row_summary(sport)] if sport is not None else [],
            "change_event_ids": sorted(event_ids),
            "notification_link_ids": sorted(row.id for row in link_rows),
            "test_only_notification_batch_ids": exclusive_batch_ids,
        },
        "counts_before": before,
        "counts_after": dict(before),
        "actions": {
            "matches_deleted": len(matches),
            "videos_deleted": len(videos),
            "tours_deleted": len(tours),
            "sport_external_ids_cleared": 1 if sport is not None else 0,
            "change_events_deleted": len(event_ids),
            "notification_links_deleted": len(link_rows),
            "notification_batches_deleted": len(exclusive_batch_ids),
        },
    }

    if dry_run:
        return report

    if event_ids:
        session.execute(delete(NotificationEventLink).where(NotificationEventLink.change_event_id.in_(event_ids)))
        session.execute(delete(ChangeEvent).where(ChangeEvent.id.in_(event_ids)))
    if exclusive_batch_ids:
        session.execute(delete(NotificationDelivery).where(NotificationDelivery.batch_id.in_(exclusive_batch_ids)))
        session.execute(delete(NotificationBatch).where(NotificationBatch.id.in_(exclusive_batch_ids)))
    for batch_id in set(affected_batch_ids) - set(exclusive_batch_ids):
        remaining = session.scalar(
            select(func.count()).select_from(NotificationEventLink).where(NotificationEventLink.batch_id == batch_id)
        ) or 0
        session.execute(update(NotificationBatch).where(NotificationBatch.id == batch_id).values(event_count=remaining))

    if videos:
        session.execute(delete(Video).where(Video.id.in_([row.id for row in videos])))
    if matches:
        session.execute(delete(Match).where(Match.id.in_([row.id for row in matches])))
    if tours:
        session.execute(delete(Tour).where(Tour.id.in_([row.id for row in tours])))
    if sport is not None:
        session.execute(update(Sport).where(Sport.id == sport.id).values(external_id=None))

    session.flush()
    report["counts_after"] = _counts(session)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove reviewed synthetic E2E fixtures from the configured database.")
    parser.add_argument("--dry-run", action="store_true", help="Report exact matches without modifying the database.")
    args = parser.parse_args()

    engine = create_db_engine()
    with get_session(engine) as session:
        report = cleanup_confirmed_test_data(session, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
