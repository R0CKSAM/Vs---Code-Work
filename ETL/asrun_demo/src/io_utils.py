"""Crash-safe file and cache helpers for the ASRUN dashboard pipeline."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


LOGGER = logging.getLogger("veto.asrun.cache")


def source_file_fingerprint(path: Path) -> dict[str, int]:
    """Return the stable local metadata used by incremental source manifests."""
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a cache manifest, rebuilding safely when it is damaged or invalid."""
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        LOGGER.warning("Ignoring unreadable cache manifest %s: %s", path, exc)
        return {}
    if not isinstance(value, dict):
        LOGGER.warning("Ignoring non-object cache manifest %s", path)
        return {}
    return value


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Publish text with a unique sibling temporary file and atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any, *, indent: int = 2) -> None:
    """Serialize and atomically publish a JSON document."""
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=True, indent=indent),
    )


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    """Write a complete Parquet file before atomically replacing its target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=path.suffix or ".parquet",
        dir=path.parent,
    )
    os.close(descriptor)
    temp_path = Path(temp_name)
    try:
        frame.to_parquet(temp_path, index=False)
        # Ensure the completed Parquet reaches the filesystem before publication.
        # Windows requires a writable descriptor for fsync on regular files.
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
