from __future__ import annotations

from app.database.models import (
    ChangeEvent,
    Match,
    NotificationBatch,
    NotificationDelivery,
    NotificationEventLink,
    Sport,
    Tour,
    Video,
)
from app.maintenance.cleanup_test_data import cleanup_confirmed_test_data


def _seed(db_session):
    sport = Sport(name="Cricket", slug="cricket", external_id="sport-1", source_url="https://www.fancode.com/cricket")
    real_tour = Tour(name="Real Tour", slug="real-tour", source_url="https://www.fancode.com/tours/real-tour")
    fixture_tour = Tour(
        external_id="tour-101", name="Indian Premier League 2026", slug="ipl-2026",
        source_url="https://www.fancode.com/tours/ipl-2026",
    )
    real_match = Match(title="Real Match", slug="real-match", source_url="https://www.fancode.com/matches/real-match")
    fixture_match = Match(
        external_id="match-e2e-501", title="E2E Initial Match", slug="e2e-initial",
        source_url="https://www.fancode.com/matches/e2e-initial",
    )
    fixture_video = Video(
        external_id="e2e-vid-101", title="Fixture Video", slug="fixture-video",
        source_url="https://www.fancode.com/video/vid-high-101",
    )
    db_session.add_all([sport, real_tour, fixture_tour, real_match, fixture_match, fixture_video])
    db_session.commit()
    return sport, real_tour, fixture_tour, real_match, fixture_match, fixture_video


def test_cleanup_dry_run_is_non_mutating(db_session):
    seeded = _seed(db_session)
    report = cleanup_confirmed_test_data(db_session, dry_run=True)

    assert report["actions"]["matches_deleted"] == 1
    assert report["actions"]["videos_deleted"] == 1
    assert report["actions"]["tours_deleted"] == 1
    assert all(db_session.get(type(row), row.id) is not None for row in seeded)


def test_cleanup_removes_only_exact_fixture_identities(db_session):
    sport, real_tour, fixture_tour, real_match, fixture_match, fixture_video = _seed(db_session)
    ids = {"sport": sport.id, "real_tour": real_tour.id, "fixture_tour": fixture_tour.id,
           "real_match": real_match.id, "fixture_match": fixture_match.id, "fixture_video": fixture_video.id}

    report = cleanup_confirmed_test_data(db_session, dry_run=False)
    db_session.commit()

    assert db_session.get(Match, ids["fixture_match"]) is None
    assert db_session.get(Video, ids["fixture_video"]) is None
    assert db_session.get(Tour, ids["fixture_tour"]) is None
    assert db_session.get(Match, ids["real_match"]) is not None
    assert db_session.get(Tour, ids["real_tour"]) is not None
    assert db_session.get(Sport, ids["sport"]) is not None
    assert db_session.get(Sport, ids["sport"]).external_id is None
    assert report["counts_before"]["matches"] - report["counts_after"]["matches"] == 1


def test_similar_but_non_exact_record_is_preserved(db_session):
    row = Match(
        external_id="match-e2e-501", title="Different source", slug="e2e-initial",
        source_url="https://www.fancode.com/matches/a-real-match",
    )
    db_session.add(row)
    db_session.commit()
    row_id = row.id

    cleanup_confirmed_test_data(db_session, dry_run=False)
    db_session.commit()

    assert db_session.get(Match, row_id) is not None


def test_cleanup_removes_direct_test_event_and_exclusive_notification_batch(db_session):
    match = Match(
        external_id="match-901", title="Fixture Match", slug="ind-vs-aus",
        source_url="https://www.fancode.com/matches/ind-vs-aus-1st-odi",
    )
    db_session.add(match)
    db_session.flush()
    event = ChangeEvent(entity_type="MATCH", entity_id=match.id, change_type="UPDATED")
    batch = NotificationBatch(batch_key="fixture-only", subject="Fixture", event_count=1)
    db_session.add_all([event, batch])
    db_session.flush()
    delivery = NotificationDelivery(batch_id=batch.id, recipient="fixture@example.test")
    link = NotificationEventLink(batch_id=batch.id, change_event_id=event.id)
    db_session.add_all([delivery, link])
    db_session.commit()
    ids = {"event": event.id, "batch": batch.id, "delivery": delivery.id, "link": link.id}

    report = cleanup_confirmed_test_data(db_session, dry_run=False)
    db_session.commit()

    assert report["actions"]["change_events_deleted"] == 1
    assert report["actions"]["notification_batches_deleted"] == 1
    assert db_session.get(ChangeEvent, ids["event"]) is None
    assert db_session.get(NotificationEventLink, ids["link"]) is None
    assert db_session.get(NotificationDelivery, ids["delivery"]) is None
    assert db_session.get(NotificationBatch, ids["batch"]) is None
