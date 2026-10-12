"""
migrations.py – Minimal schema migration and initialization support.

Wraps metadata creation and table inspection. Structured cleanly so Alembic
can be dropped in during future phases without altering model definitions.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import Engine, inspect

from app.database.connection import Base, create_db_engine, init_db

logger = logging.getLogger(__name__)


def get_existing_tables(engine: Optional[Engine] = None) -> list[str]:
    """Return a list of all table names currently in the database."""
    eng = engine or create_db_engine()
    inspector = inspect(eng)
    return inspector.get_table_names()


def verify_schema(engine: Optional[Engine] = None) -> bool:
    """Verify that all model tables exist in the database."""
    tables = set(get_existing_tables(engine))
    expected = set(Base.metadata.tables.keys())
    return expected.issubset(tables)


def run_migrations(engine: Optional[Engine] = None) -> None:
    """
    Run schema migrations / initialization.
    Safe to execute repeatedly without data loss.
    """
    eng = engine or create_db_engine()
    init_db(eng)
    logger.info("Schema migration/initialization finished. Tables verified: %s", verify_schema(eng))


if __name__ == "__main__":
    import sys
    print("Running database migrations...")
    run_migrations()
    print("Database migration completed successfully.")
    sys.exit(0)
