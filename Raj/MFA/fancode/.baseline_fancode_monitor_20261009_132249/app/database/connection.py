"""
connection.py – Database engine, session lifecycle, and initialization.

Uses modern SQLAlchemy 2.x patterns. Supports configurable database URL,
SQLite connection optimizations (foreign keys enabled), and thread-safe session factories.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)

from app.config.settings import settings

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def _enable_sqlite_foreign_keys(dbapi_con, con_record):
    """Enable SQLite foreign key support on every newly opened connection."""
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_url: Optional[str] = None, echo: Optional[bool] = None) -> Engine:
    """
    Create and configure a SQLAlchemy 2.x Engine.
    Ensures parent directories exist if connecting to a file-based SQLite DB.
    """
    url = db_url or settings.DATABASE_URL
    echo_mode = echo if echo is not None else settings.DATABASE_ECHO

    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        # Extract relative or absolute path from sqlite:///path
        file_path_str = url.replace("sqlite:///", "")
        db_file = Path(file_path_str)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        url,
        echo=echo_mode,
        future=True,
    )

    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    logger.debug("Database engine created for URL: %s", url)
    return engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the given or default engine."""
    eng = engine or create_db_engine()
    return sessionmaker(
        bind=eng,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def get_session(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """
    Context manager providing a transactional Session scope.
    Automatically commits on success or rolls back on exception.
    """
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Transaction rolled back due to error: %s", exc)
        raise
    finally:
        session.close()


def _upgrade_schema(engine: Engine) -> None:
    """
    Inspects existing database schema and safely adds any missing columns or indexes
    defined in SQLAlchemy ORM models without data loss.
    Idempotent and safe to run on fresh or pre-existing databases.
    """
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for column in table.columns:
                if column.name not in existing_columns:
                    col_type = column.type.compile(engine.dialect)
                    default_clause = ""
                    if column.default is not None and hasattr(column.default, "arg"):
                        default_val = column.default.arg
                        if isinstance(default_val, (int, float)):
                            default_clause = f" DEFAULT {default_val}"
                        elif isinstance(default_val, str):
                            default_clause = f" DEFAULT '{default_val}'"
                        elif isinstance(default_val, bool):
                            default_clause = f" DEFAULT {1 if default_val else 0}"
                    elif not column.nullable:
                        default_clause = " DEFAULT ''"

                    sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_clause}"
                    logger.info("Upgrading schema: adding column %s.%s (%s)", table_name, column.name, col_type)
                    conn.execute(text(sql))
                    existing_columns.add(column.name)

                    if column.index:
                        idx_name = f"ix_{table_name}_{column.name}"
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({column.name})"))

        conn.commit()


def init_db(engine: Optional[Engine] = None) -> None:
    """
    Initialize database schema (create all tables and upgrade pre-existing tables).
    Safe to run repeatedly; does not destroy existing data.
    """
    # Import models so they are registered with Base.metadata
    from app.database import models  # noqa: F401

    eng = engine or create_db_engine()
    Base.metadata.create_all(bind=eng)
    _upgrade_schema(eng)
    logger.info("Database initialized and schema verified successfully.")
