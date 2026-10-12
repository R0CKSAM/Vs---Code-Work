"""
grouping.py – Deterministic event grouping and batching for FanCode notifications (Phase 9).
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.notifications.models import GroupedEntity, NotificationBatchDraft

logger = logging.getLogger(__name__)


class EventGrouper:
    """
    Groups individual ChangeEvents into deterministic notification batches and entity digests.
    """

    @classmethod
    def compute_batch_key(cls, events: List[Any], scrape_run_id: Optional[int] = None) -> str:
        """
        Computes a deterministic unique SHA256 key for a set of ChangeEvents.
        Ensures repeated runs over the same events produce identical batch keys.
        """
        if not events:
            return hashlib.sha256(b"empty").hexdigest()

        event_keys: List[str] = []
        for e in events:
            e_id = getattr(e, "id", None) or 0
            e_type = getattr(e, "entity_type", "")
            e_entity_id = getattr(e, "entity_id", 0)
            c_type = getattr(e, "change_type", "")
            f_name = getattr(e, "field_name", "") or ""
            n_val = getattr(e, "new_value", "") or ""
            event_keys.append(f"{e_id}:{e_type}:{e_entity_id}:{c_type}:{f_name}:{n_val}")

        event_keys.sort()
        prefix = f"run-{scrape_run_id}:" if scrape_run_id is not None else "batch:"
        serialized = prefix + ";".join(event_keys)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def group_by_entity(cls, events: List[Any]) -> List[GroupedEntity]:
        """
        Aggregates events belonging to the same logical entity (entity_type + entity_id / external_id).
        """
        grouped_dict: Dict[tuple[str, int], List[Any]] = defaultdict(list)
        entity_meta: Dict[tuple[str, int], Dict[str, Any]] = {}

        for e in events:
            e_type = (getattr(e, "entity_type", "") or "").upper()
            e_id = getattr(e, "entity_id", 0)
            key = (e_type, e_id)
            grouped_dict[key].append(e)

            meta = getattr(e, "metadata_json", None)
            if not isinstance(meta, dict):
                meta = getattr(e, "metadata", None)
            if not isinstance(meta, dict):
                meta = {}

            if key not in entity_meta:
                entity_meta[key] = {
                    "external_id": getattr(e, "external_id", None) or meta.get("external_id"),
                    "source_url": getattr(e, "source_url", None) or meta.get("source_url"),
                    "title": (
                        meta.get("title")
                        or meta.get("name")
                        or (getattr(e, "new_value", None) if getattr(e, "change_type", "") == "CREATED" else None)
                        or meta.get("current_raw")
                    ),
                    "sport_name": meta.get("sport") or meta.get("sport_name"),
                    "tour_name": meta.get("tour") or meta.get("tour_name") or meta.get("competition"),
                }
            else:
                current_info = entity_meta[key]
                if not current_info["external_id"]:
                    current_info["external_id"] = getattr(e, "external_id", None) or meta.get("external_id")
                if not current_info["source_url"]:
                    current_info["source_url"] = getattr(e, "source_url", None) or meta.get("source_url")
                if not current_info["title"] or current_info["title"].lower().startswith("match"):
                    candidate_title = (
                        meta.get("title")
                        or meta.get("name")
                        or (getattr(e, "new_value", None) if getattr(e, "change_type", "") == "CREATED" else None)
                        or meta.get("current_raw")
                    )
                    if candidate_title:
                        current_info["title"] = candidate_title
                if not current_info["sport_name"]:
                    current_info["sport_name"] = meta.get("sport") or meta.get("sport_name")
                if not current_info["tour_name"]:
                    current_info["tour_name"] = meta.get("tour") or meta.get("tour_name") or meta.get("competition")

        grouped_entities: List[GroupedEntity] = []
        for (e_type, e_id), evts in grouped_dict.items():
            info = entity_meta[(e_type, e_id)]
            grouped_entities.append(
                GroupedEntity(
                    entity_type=e_type,
                    entity_id=e_id,
                    external_id=info["external_id"],
                    title=info["title"],
                    source_url=info["source_url"],
                    events=evts,
                    sport_name=info["sport_name"],
                    tour_name=info["tour_name"],
                )
            )

        # Sort entities deterministically (by type, then ID)
        grouped_entities.sort(key=lambda g: (g.entity_type, g.entity_id))
        return grouped_entities

    @classmethod
    def create_batch(
        cls,
        events: List[Any],
        scrape_run_id: Optional[int] = None,
        max_events: Optional[int] = None,
    ) -> Optional[NotificationBatchDraft]:
        """
        Groups notifiable events into a single notification batch draft.
        Returns None if events list is empty.
        """
        if not events:
            return None

        batch_events = events[:max_events] if max_events else list(events)
        batch_key = cls.compute_batch_key(batch_events, scrape_run_id)
        grouped = cls.group_by_entity(batch_events)

        return NotificationBatchDraft(
            batch_key=batch_key,
            events=batch_events,
            grouped_entities=grouped,
            scrape_run_id=scrape_run_id,
        )
