from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingested_objects (
    object_key TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    status TEXT NOT NULL,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    processing_ms INTEGER,
    error_message TEXT,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS minute_clients (
    minute TEXT NOT NULL,
    stream TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT '',
    requests INTEGER NOT NULL DEFAULT 0,
    errors_4xx INTEGER NOT NULL DEFAULT 0,
    errors_5xx INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (minute, stream, client_ip, state)
);

CREATE INDEX IF NOT EXISTS idx_minute_clients_stream_minute
ON minute_clients(stream, minute);

CREATE TABLE IF NOT EXISTS pipeline_status (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_status(conn: sqlite3.Connection, key: str, value: object) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO pipeline_status(key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, str(value), now),
    )

