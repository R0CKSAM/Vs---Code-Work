"""Consistent SQLite backup helpers, including databases operating in WAL mode."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_sqlite_backup(source: Path, destination: Path) -> Path:
    """Create and validate an online SQLite snapshot.

    Copying only the main ``.db`` file can silently omit committed pages still
    present in ``-wal``. SQLite's backup API reads one coherent transaction.
    """
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)

    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)

    with sqlite3.connect(f"file:{destination.as_posix()}?mode=ro", uri=True) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"SQLite backup integrity check failed: {integrity!r}")
    return destination
