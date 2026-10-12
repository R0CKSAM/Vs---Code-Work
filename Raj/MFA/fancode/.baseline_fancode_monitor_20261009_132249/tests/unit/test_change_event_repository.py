"""
Unit tests for ChangeEventsRepository (Phase 8).
"""

import pytest
from app.database.models import ChangeEvent
from app.database.repositories import ChangeEventsRepository


class TestChangeEventsRepository:
    def test_create_and_find_existing_event(self, db_session):
        repo = ChangeEventsRepository(db_session)
        event = repo.create(
            entity_type="MATCH",
            entity_id=1,
            change_type="STATUS_CHANGED",
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity="CRITICAL",
        )
        assert event.id is not None
        assert event.detected_at is not None

        # Find exact match
        found = repo.find_existing_event(
            entity_type="MATCH",
            entity_id=1,
            change_type="STATUS_CHANGED",
            field_name="status",
            new_value="LIVE",
        )
        assert found is not None
        assert found.id == event.id

        # Non-matching entity_id returns None
        assert repo.find_existing_event(
            entity_type="MATCH",
            entity_id=999,
            change_type="STATUS_CHANGED",
            field_name="status",
            new_value="LIVE",
        ) is None

    def test_get_for_entity(self, db_session):
        repo = ChangeEventsRepository(db_session)
        repo.create(entity_type="MATCH", entity_id=10, change_type="CREATED")
        repo.create(entity_type="MATCH", entity_id=10, change_type="UPDATED", field_name="venue")
        repo.create(entity_type="VIDEO", entity_id=10, change_type="CREATED")

        events = repo.get_for_entity("MATCH", 10)
        assert len(events) == 2
        assert all(e.entity_type == "MATCH" and e.entity_id == 10 for e in events)

    def test_unnotified_events_and_mark_notified(self, db_session):
        repo = ChangeEventsRepository(db_session)
        ev1 = repo.create(entity_type="MATCH", entity_id=5, change_type="CREATED")
        ev2 = repo.create(entity_type="MATCH", entity_id=6, change_type="CREATED")

        unnotified = repo.get_unnotified()
        unnotified_ids = [e.id for e in unnotified]
        assert ev1.id in unnotified_ids
        assert ev2.id in unnotified_ids

        repo.mark_notified(ev1.id)
        assert ev1.notified_at is not None

        remaining = repo.get_unnotified()
        assert ev1.id not in [e.id for e in remaining]
        assert ev2.id in [e.id for e in remaining]
