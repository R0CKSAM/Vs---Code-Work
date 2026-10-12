"""
conftest.py – Global pytest configuration and shared database fixtures for unit and integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import Base
from app.config.settings import settings


PRODUCTION_DATABASE_PATH = (ROOT / "data" / "fancode.db").resolve()


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database(tmp_path_factory):
    """Force every default application DB call onto a disposable test database."""
    test_db_path = (tmp_path_factory.mktemp("fancode-db") / "fancode-test.db").resolve()
    original_url = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite:///{test_db_path.as_posix()}"
    try:
        yield test_db_path
    finally:
        settings.DATABASE_URL = original_url


@pytest.fixture
def test_engine():
    """Create an isolated in-memory SQLite engine with tables created."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Provide an isolated database session rolled back and closed after each test."""
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()
