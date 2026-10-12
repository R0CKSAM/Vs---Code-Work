"""
test_notification_grouping.py – Unit tests for Phase 9 EventGrouper and digest batching.
"""

from __future__ import annotations

import pytest
from app.change_detection.models import ChangeType, EntityType, ProposedChangeEvent, Severity
from app.notifications.grouping import EventGrouper


class TestNotificationGrouping:
    def test_multiple_events_become_one_digest_batch(self):
        events = [
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=101,
                change_type=ChangeType.CREATED.value,
                new_value="Match A",
                severity=Severity.IMPORTANT.value,
            ),
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=102,
                change_type=ChangeType.STATUS_CHANGED.value,
                new_value="LIVE",
                severity=Severity.CRITICAL.value,
            ),
            ProposedChangeEvent(
                entity_type=EntityType.VIDEO.value,
                entity_id=201,
                change_type=ChangeType.CREATED.value,
                new_value="Video Highlights",
                severity=Severity.INFO.value,
            ),
        ]

        batch = EventGrouper.create_batch(events, scrape_run_id=1)
        assert batch is not None
        assert batch.event_count == 3
        assert len(batch.grouped_entities) == 3

    def test_events_for_same_entity_are_grouped(self):
        events = [
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=101,
                change_type=ChangeType.UPDATED.value,
                field_name="venue",
                new_value="DY Patil Stadium",
            ),
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=101,
                change_type=ChangeType.STATUS_CHANGED.value,
                field_name="status",
                new_value="LIVE",
            ),
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=101,
                change_type=ChangeType.UPDATED.value,
                field_name="title",
                new_value="MI vs CSK Final",
            ),
        ]

        batch = EventGrouper.create_batch(events)
        assert batch is not None
        assert batch.event_count == 3
        assert len(batch.grouped_entities) == 1
        assert batch.grouped_entities[0].entity_id == 101
        assert len(batch.grouped_entities[0].events) == 3

    def test_different_entities_remain_separately_represented(self):
        events = [
            ProposedChangeEvent(
                entity_type=EntityType.MATCH.value,
                entity_id=101,
                change_type=ChangeType.STATUS_CHANGED.value,
                new_value="LIVE",
            ),
            ProposedChangeEvent(
                entity_type=EntityType.VIDEO.value,
                entity_id=201,
                change_type=ChangeType.CREATED.value,
                new_value="Top Wickets",
            ),
        ]

        grouped = EventGrouper.group_by_entity(events)
        assert len(grouped) == 2
        types = {g.entity_type for g in grouped}
        assert types == {EntityType.MATCH.value, EntityType.VIDEO.value}

    def test_grouping_batch_key_is_deterministic(self):
        ev1 = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            new_value="LIVE",
        )
        ev2 = ProposedChangeEvent(
            entity_type=EntityType.VIDEO.value,
            entity_id=201,
            change_type=ChangeType.CREATED.value,
            field_name=None,
            new_value="Highlights",
        )

        key1 = EventGrouper.compute_batch_key([ev1, ev2], scrape_run_id=42)
        key2 = EventGrouper.compute_batch_key([ev2, ev1], scrape_run_id=42)
        assert key1 == key2

    def test_empty_event_set_produces_none_batch(self):
        batch = EventGrouper.create_batch([])
        assert batch is None
