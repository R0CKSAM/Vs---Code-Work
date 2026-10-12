"""
detector.py – Main Change Detection Engine for FanCode entities.

Executes state comparison against database entities, performs deduplication,
respects meaningful field policies, ensures removal safety, and transactionally
persists ChangeEvent audit records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Type

from sqlalchemy.orm import Session

from app.change_detection.classifier import ChangeClassifier
from app.change_detection.comparator import StateComparator
from app.change_detection.models import (
    ChangeDetectionResult,
    ChangeType,
    EntityType,
    ProposedChangeEvent,
    Severity,
)
from app.database.models import ChangeEvent, Match, Sport, Tour, Video
from app.database.repositories import ChangeEventsRepository

logger = logging.getLogger(__name__)


class ChangeDetector:
    """
    Production-quality Change Detection Engine.

    Compares current state against persisted database state, evaluates field
    significance, checks event deduplication, and records change events.
    """

    def __init__(
        self,
        session: Session,
        baseline_data: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        self.session = session
        self.repo = ChangeEventsRepository(session)
        self.baseline_data = baseline_data or {}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def detect_matches(
        self,
        current_data_list: List[Dict[str, Any]],
        scrape_run_id: Optional[int] = None,
        complete_snapshot: bool = False,
        dry_run: bool = False,
    ) -> ChangeDetectionResult:
        """Run change detection over a batch of matches."""
        return self._detect_for_entity(
            entity_type=EntityType.MATCH.value,
            model_class=Match,
            current_data_list=current_data_list,
            id_field="external_id",
            scrape_run_id=scrape_run_id,
            complete_snapshot=complete_snapshot,
            dry_run=dry_run,
        )

    def detect_sports(
        self,
        current_data_list: List[Dict[str, Any]],
        scrape_run_id: Optional[int] = None,
        complete_snapshot: bool = False,
        dry_run: bool = False,
    ) -> ChangeDetectionResult:
        """Run change detection over sports."""
        return self._detect_for_entity(
            entity_type=EntityType.SPORT.value,
            model_class=Sport,
            current_data_list=current_data_list,
            id_field="slug",
            scrape_run_id=scrape_run_id,
            complete_snapshot=complete_snapshot,
            dry_run=dry_run,
        )

    def detect_tours(
        self,
        current_data_list: List[Dict[str, Any]],
        scrape_run_id: Optional[int] = None,
        complete_snapshot: bool = False,
        dry_run: bool = False,
    ) -> ChangeDetectionResult:
        """Run change detection over tours."""
        return self._detect_for_entity(
            entity_type=EntityType.TOUR.value,
            model_class=Tour,
            current_data_list=current_data_list,
            id_field="slug",
            scrape_run_id=scrape_run_id,
            complete_snapshot=complete_snapshot,
            dry_run=dry_run,
        )

    def detect_videos(
        self,
        current_data_list: List[Dict[str, Any]],
        scrape_run_id: Optional[int] = None,
        complete_snapshot: bool = False,
        dry_run: bool = False,
    ) -> ChangeDetectionResult:
        """Run change detection over videos."""
        return self._detect_for_entity(
            entity_type=EntityType.VIDEO.value,
            model_class=Video,
            current_data_list=current_data_list,
            id_field="slug",
            scrape_run_id=scrape_run_id,
            complete_snapshot=complete_snapshot,
            dry_run=dry_run,
        )

    def detect_all(
        self,
        matches_data: Optional[List[Dict[str, Any]]] = None,
        sports_data: Optional[List[Dict[str, Any]]] = None,
        tours_data: Optional[List[Dict[str, Any]]] = None,
        videos_data: Optional[List[Dict[str, Any]]] = None,
        scrape_run_id: Optional[int] = None,
        complete_snapshot: bool = False,
        dry_run: bool = False,
    ) -> ChangeDetectionResult:
        """Run change detection across all entity categories."""
        combined = ChangeDetectionResult()

        suites = [
            (self.detect_matches, matches_data),
            (self.detect_sports, sports_data),
            (self.detect_tours, tours_data),
            (self.detect_videos, videos_data),
        ]

        for detector_fn, data in suites:
            if data is not None:
                res = detector_fn(
                    current_data_list=data,
                    scrape_run_id=scrape_run_id,
                    complete_snapshot=complete_snapshot,
                    dry_run=dry_run,
                )
                self._merge_results(combined, res)

        return combined

    # -------------------------------------------------------------------------
    # Internal Engine Logic
    # -------------------------------------------------------------------------

    def _detect_for_entity(
        self,
        entity_type: str,
        model_class: Type[Any],
        current_data_list: List[Dict[str, Any]],
        id_field: str,
        scrape_run_id: Optional[int],
        complete_snapshot: bool,
        dry_run: bool,
    ) -> ChangeDetectionResult:
        result = ChangeDetectionResult()
        meaningful_fields = ChangeClassifier.get_meaningful_fields(entity_type)

        # 1. Map existing records from DB
        existing_records: List[Any]
        if entity_type in self.baseline_data:
            existing_records = list(self.baseline_data[entity_type])
        else:
            existing_records = list(self.session.query(model_class).all())

        def record_value(record: Any, name: str, default: Any = None) -> Any:
            return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)

        existing_by_key: Dict[str, Any] = {}
        for rec in existing_records:
            key_val = record_value(rec, id_field)
            if key_val is not None:
                existing_by_key[str(key_val)] = rec
            ext_id = record_value(rec, "external_id")
            if ext_id:
                existing_by_key[f"ext:{ext_id}"] = rec
            src_url = record_value(rec, "source_url")
            if src_url:
                existing_by_key[f"url:{src_url}"] = rec

        observed_keys: Set[str] = set()

        # 2. Iterate current incoming items
        for item in current_data_list:
            result.entities_checked += 1
            key_val = item.get(id_field) or item.get("match_id")
            ext_id = item.get("external_id")
            source_url = item.get("source_url")

            lookup_key = str(key_val) if key_val is not None else (f"ext:{ext_id}" if ext_id else None)
            if not lookup_key and source_url:
                lookup_key = f"url:{source_url}"

            if not lookup_key:
                logger.warning("Skipping item without identifiable key: %s", item)
                continue

            observed_keys.add(lookup_key)
            existing_rec = existing_by_key.get(lookup_key)
            if not existing_rec and ext_id:
                existing_rec = existing_by_key.get(f"ext:{ext_id}")
            if not existing_rec and source_url:
                existing_rec = existing_by_key.get(f"url:{source_url}")

            if existing_rec is None:
                # CREATED / NEW entity
                entity_title = item.get("title") or item.get("name")
                # Scraper stages persist before detection. Resolve the newly
                # inserted row so audit events reference the real entity ID.
                current_rec = None
                if ext_id:
                    current_rec = self.session.query(model_class).filter(
                        getattr(model_class, "external_id") == str(ext_id)
                    ).first()
                if current_rec is None and source_url:
                    current_rec = self.session.query(model_class).filter(
                        getattr(model_class, "source_url") == source_url
                    ).first()
                event = ProposedChangeEvent(
                    entity_type=entity_type,
                    entity_id=getattr(current_rec, "id", 0),
                    change_type=ChangeType.CREATED.value,
                    field_name=None,
                    old_value=None,
                    new_value=StateComparator.normalize_for_comparison(entity_title),
                    severity=ChangeClassifier.classify_severity(entity_type, ChangeType.CREATED.value),
                    external_id=str(ext_id or key_val),
                    source_url=source_url,
                    scrape_run_id=scrape_run_id,
                    metadata={"title": entity_title, "details": "New entity discovered"},
                )
                self._process_event(event, result, dry_run)
            else:
                # Existing entity – compare tracked meaningful fields
                observed_keys.add(str(record_value(existing_rec, id_field, "")))
                existing_data = (
                    dict(existing_rec)
                    if isinstance(existing_rec, dict)
                    else {col.name: getattr(existing_rec, col.name) for col in existing_rec.__table__.columns}
                )
                changed_diff = StateComparator.compare_fields(existing_data, item, meaningful_fields)
                entity_title = record_value(existing_rec, "title") or record_value(existing_rec, "name") or item.get("title") or item.get("name")

                for field_name, (norm_old, norm_new) in changed_diff.items():
                    # Classify change
                    classification = ChangeClassifier.classify_field_change(
                        entity_type=entity_type,
                        field_name=field_name,
                        old_value=norm_old,
                        new_value=norm_new,
                    )
                    if not classification:
                        continue
                    change_type, severity = classification

                    event = ProposedChangeEvent(
                        entity_type=entity_type,
                        entity_id=int(record_value(existing_rec, "id", 0)),
                        change_type=change_type,
                        field_name=field_name,
                        old_value=norm_old,
                        new_value=norm_new,
                        severity=severity,
                        external_id=str(ext_id or record_value(existing_rec, "external_id", "") or key_val),
                        source_url=source_url or record_value(existing_rec, "source_url"),
                        scrape_run_id=scrape_run_id,
                        metadata={
                            "title": entity_title,
                            "previous_raw": str(existing_data.get(field_name)),
                            "current_raw": str(item.get(field_name)),
                        },
                    )
                    self._process_event(event, result, dry_run)

        # 3. Removal Check (Only when complete_snapshot=True)
        # Never trigger REMOVED if the scrape was empty or partial
        if complete_snapshot and len(current_data_list) > 0:
            for rec in existing_records:
                rec_key = str(record_value(rec, id_field, ""))
                rec_ext = f"ext:{record_value(rec, 'external_id', '')}"
                if rec_key not in observed_keys and rec_ext not in observed_keys:
                    entity_title = record_value(rec, "title") or record_value(rec, "name")
                    event = ProposedChangeEvent(
                        entity_type=entity_type,
                        entity_id=int(record_value(rec, "id", 0)),
                        change_type=ChangeType.REMOVED.value,
                        field_name=None,
                        old_value=StateComparator.normalize_for_comparison(entity_title),
                        new_value=None,
                        severity=Severity.IMPORTANT.value,
                        external_id=record_value(rec, "external_id"),
                        source_url=record_value(rec, "source_url"),
                        scrape_run_id=scrape_run_id,
                        metadata={"title": entity_title, "reason": "Entity omitted from authoritative complete snapshot"},
                    )
                    self._process_event(event, result, dry_run)

        return result

    def _process_event(
        self,
        event: ProposedChangeEvent,
        result: ChangeDetectionResult,
        dry_run: bool,
    ) -> None:
        """Deduplicate and optionally persist an event."""
        # 1. Deduplication check in DB
        existing = self.repo.find_existing_event(
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            change_type=event.change_type,
            field_name=event.field_name,
            new_value=event.new_value,
        )

        if existing is not None:
            # Duplicate event already recorded previously; ignore
            result.ignored_changes += 1
            return

        # 2. Check if already added in the current batch result.events
        for past_ev in result.events:
            if past_ev.event_key == event.event_key:
                result.ignored_changes += 1
                return

        # 3. Add to result
        result.events.append(event)
        if event.change_type == ChangeType.CREATED.value:
            result.created_events += 1
        elif event.change_type == ChangeType.STATUS_CHANGED.value:
            result.status_events += 1
        elif event.change_type == ChangeType.REMOVED.value:
            result.removed_events += 1
        else:
            result.updated_events += 1

        # 4. Persistence if not dry_run
        if not dry_run:
            self.repo.create(
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                external_id=event.external_id,
                change_type=event.change_type,
                field_name=event.field_name,
                old_value=event.old_value,
                new_value=event.new_value,
                source_url=event.source_url,
                severity=event.severity,
                scrape_run_id=event.scrape_run_id,
                metadata_json=event.metadata,
                detected_at=event.detected_at,
            )

    @staticmethod
    def _merge_results(base: ChangeDetectionResult, added: ChangeDetectionResult) -> None:
        base.entities_checked += added.entities_checked
        base.created_events += added.created_events
        base.updated_events += added.updated_events
        base.status_events += added.status_events
        base.removed_events += added.removed_events
        base.ignored_changes += added.ignored_changes
        base.errors += added.errors
        base.events.extend(added.events)
