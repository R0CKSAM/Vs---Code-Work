from __future__ import annotations

import hashlib

from app.config.settings import settings
from app.database.connection import get_session, init_db
from app.database.models import Match
from app.database.repositories import MatchesRepository
from tests.conftest import PRODUCTION_DATABASE_PATH


def test_default_test_database_is_not_production(isolated_test_database):
    assert isolated_test_database != PRODUCTION_DATABASE_PATH
    assert settings.DATABASE_URL == f"sqlite:///{isolated_test_database.as_posix()}"


def test_e2e_fixture_write_cannot_modify_production_database(isolated_test_database):
    before_exists = PRODUCTION_DATABASE_PATH.exists()
    before_hash = hashlib.sha256(PRODUCTION_DATABASE_PATH.read_bytes()).hexdigest() if before_exists else None

    init_db()
    with get_session() as session:
        MatchesRepository(session).upsert(
            external_id="match-e2e-501",
            title="E2E Initial Match",
            slug="e2e-initial",
            source_url="https://www.fancode.com/matches/e2e-initial",
            status="UPCOMING",
        )

    assert isolated_test_database.exists()
    assert PRODUCTION_DATABASE_PATH.exists() is before_exists
    after_hash = hashlib.sha256(PRODUCTION_DATABASE_PATH.read_bytes()).hexdigest() if before_exists else None
    assert after_hash == before_hash

    with get_session() as session:
        assert session.query(Match).filter_by(external_id="match-e2e-501").count() == 1
