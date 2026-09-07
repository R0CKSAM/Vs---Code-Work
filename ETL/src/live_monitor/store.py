from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
import time
from pathlib import Path
from typing import Iterator

from .parser import FileBatch, GLOBAL_TARGET, IST


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=10000;
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    stable_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'observed',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    discovered_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0,
    min_event_ts REAL,
    max_event_ts REAL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS files_claim_idx
    ON files(status, next_attempt_at, mtime_ns DESC);
CREATE TABLE IF NOT EXISTS minute_metrics (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    requests INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    errors_4xx INTEGER NOT NULL,
    errors_5xx INTEGER NOT NULL,
    media_segments INTEGER NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target)
);
CREATE TABLE IF NOT EXISTS minute_viewers (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    viewer_key TEXT NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target, viewer_key)
);
CREATE INDEX IF NOT EXISTS minute_viewers_target_idx
    ON minute_viewers(target, minute_ist);
CREATE TABLE IF NOT EXISTS minute_devices (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    device_key TEXT NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target, device_key)
);
CREATE INDEX IF NOT EXISTS minute_devices_target_idx
    ON minute_devices(target, minute_ist);
CREATE TABLE IF NOT EXISTS minute_sessions (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    session_key TEXT NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target, session_key)
);
CREATE INDEX IF NOT EXISTS minute_sessions_target_idx
    ON minute_sessions(target, minute_ist);
CREATE TABLE IF NOT EXISTS minute_dimensions (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    requests INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target, dimension, value)
);
CREATE INDEX IF NOT EXISTS minute_dimensions_target_idx
    ON minute_dimensions(target, dimension, minute_ist);
CREATE TABLE IF NOT EXISTS daily_viewers (
    date_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    viewer_key TEXT NOT NULL,
    PRIMARY KEY(date_ist, req_host, target, viewer_key)
);
CREATE INDEX IF NOT EXISTS daily_viewers_target_idx
    ON daily_viewers(target, date_ist);
CREATE TABLE IF NOT EXISTS runtime_events (
    occurred_at REAL NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class LiveStore:
    """SQLite-backed exact-once file ledger and durable minute aggregates."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def recover(self, _stale_seconds: int) -> int:
        """Immediately requeue interrupted work after the single-instance lock is held."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE files
                   SET status='pending', updated_at=?,
                       error='Recovered after interrupted processing'
                 WHERE status='processing'
                """,
                (time.time(),),
            )
            return cursor.rowcount

    def ensure_channel_mapping_version(self, version: int) -> int:
        """Atomically invalidate aggregates when channel resolution changes."""
        value = str(version)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='channel_mapping_version'"
            ).fetchone()
            if row is not None and row["value"] == value:
                return 0
            count = int(connection.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            connection.execute("DELETE FROM minute_metrics")
            connection.execute("DELETE FROM minute_viewers")
            connection.execute("DELETE FROM minute_devices")
            connection.execute("DELETE FROM minute_sessions")
            connection.execute("DELETE FROM minute_dimensions")
            connection.execute("DELETE FROM daily_viewers")
            connection.execute(
                """
                UPDATE files SET status='pending',attempts=0,next_attempt_at=0,
                    rows=0,rejected_rows=0,min_event_ts=NULL,max_event_ts=NULL,error=NULL,
                    updated_at=?
                """,
                (time.time(),),
            )
            connection.execute(
                """
                INSERT INTO metadata(key,value) VALUES('channel_mapping_version',?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (value,),
            )
            return count

    def file_signatures(self) -> dict[str, tuple[int, int]]:
        """Load durable file signatures so filesystem scans avoid DB round trips."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT path,size,mtime_ns FROM files WHERE status <> 'observed'"
            ).fetchall()
        return {
            str(row["path"]): (int(row["size"]), int(row["mtime_ns"]))
            for row in rows
        }

    def observe_file(
        self, path: Path, size: int, mtime_ns: int, stable_observations: int
    ) -> str:
        now = time.time()
        path_text = str(path.resolve())
        with self.connect() as connection:
            row = connection.execute(
                "SELECT size,mtime_ns,stable_count,status FROM files WHERE path=?",
                (path_text,),
            ).fetchone()
            if row is None:
                stable_count = 1
                status = "pending" if stable_observations <= 1 else "observed"
                connection.execute(
                    """
                    INSERT INTO files(
                        path,size,mtime_ns,stable_count,status,discovered_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (path_text, size, mtime_ns, stable_count, status, now, now),
                )
                return status
            if row["size"] == size and row["mtime_ns"] == mtime_ns:
                if row["status"] not in {"observed", "pending"}:
                    return str(row["status"])
                stable_count = int(row["stable_count"]) + 1
                status = "pending" if stable_count >= stable_observations else "observed"
                connection.execute(
                    "UPDATE files SET stable_count=?,status=?,updated_at=? WHERE path=?",
                    (stable_count, status, now, path_text),
                )
                return status
            if row["status"] == "done":
                connection.execute(
                    "UPDATE files SET status='changed',error=?,updated_at=? WHERE path=?",
                    ("Completed file changed on disk; refusing to double count", now, path_text),
                )
                return "changed"
            connection.execute(
                """
                UPDATE files
                   SET size=?,mtime_ns=?,stable_count=1,status='observed',
                       attempts=0,next_attempt_at=0,error=NULL,updated_at=?
                 WHERE path=?
                """,
                (size, mtime_ns, now, path_text),
            )
            return "observed"

    def claim_file(self) -> Path | None:
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT path FROM files
                 WHERE status='pending' AND next_attempt_at <= ?
                 ORDER BY mtime_ns DESC LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE files SET status='processing',attempts=attempts+1,updated_at=?
                 WHERE path=? AND status='pending'
                """,
                (now, row["path"]),
            ).rowcount
            return Path(row["path"]) if updated else None

    def finish_file(self, path: Path, batch: FileBatch) -> None:
        path_text = str(path.resolve())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            status = connection.execute(
                "SELECT status FROM files WHERE path=?", (path_text,)
            ).fetchone()
            if status is None or status["status"] != "processing":
                raise RuntimeError(f"File is not claimed for processing: {path}")
            connection.executemany(
                """
                INSERT INTO minute_metrics(
                    minute_ist,req_host,target,requests,bytes,errors_4xx,errors_5xx,
                    media_segments
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(minute_ist,req_host,target) DO UPDATE SET
                    requests=requests+excluded.requests,
                    bytes=bytes+excluded.bytes,
                    errors_4xx=errors_4xx+excluded.errors_4xx,
                    errors_5xx=errors_5xx+excluded.errors_5xx,
                    media_segments=media_segments+excluded.media_segments
                """,
                [(*key, *values) for key, values in batch.metrics.items()],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO minute_viewers VALUES(?,?,?,?)",
                batch.minute_viewers,
            )
            connection.executemany(
                "INSERT OR IGNORE INTO minute_devices VALUES(?,?,?,?)",
                batch.minute_devices,
            )
            connection.executemany(
                "INSERT OR IGNORE INTO minute_sessions VALUES(?,?,?,?)",
                batch.minute_sessions,
            )
            connection.executemany(
                """
                INSERT INTO minute_dimensions(
                    minute_ist,req_host,target,dimension,value,requests,bytes
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(minute_ist,req_host,target,dimension,value) DO UPDATE SET
                    requests=requests+excluded.requests,
                    bytes=bytes+excluded.bytes
                """,
                [(*key, *values) for key, values in batch.dimensions.items()],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO daily_viewers VALUES(?,?,?,?)",
                batch.daily_viewers,
            )
            connection.execute(
                """
                UPDATE files SET status='done',rows=?,rejected_rows=?,max_event_ts=?,
                    updated_at=?,error=NULL WHERE path=?
                """,
                (
                    batch.rows,
                    batch.rejected_rows,
                    batch.latest_timestamp,
                    time.time(),
                    path_text,
                ),
            )

    def fail_file(self, path: Path, message: str, max_attempts: int = 5) -> None:
        now = time.time()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT attempts FROM files WHERE path=?", (str(path.resolve()),)
            ).fetchone()
            attempts = int(row["attempts"]) if row else max_attempts
            status = "failed" if attempts >= max_attempts else "pending"
            delay = min(300, 5 * (2 ** max(0, attempts - 1)))
            connection.execute(
                """
                UPDATE files SET status=?,next_attempt_at=?,error=?,updated_at=?
                 WHERE path=?
                """,
                (status, now + delay, message[:1000], now, str(path.resolve())),
            )
        self.event("ERROR", "parser", f"{path.name}: {message}")

    def event(self, level: str, component: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runtime_events VALUES(?,?,?,?)",
                (time.time(), level, component, message[:2000]),
            )
            connection.execute(
                """
                DELETE FROM runtime_events WHERE rowid NOT IN (
                    SELECT rowid FROM runtime_events ORDER BY occurred_at DESC LIMIT 500
                )
                """
            )

    def snapshot(self, dashboard_minutes: int) -> dict:
        cutoff = (
            dt.datetime.now(IST) - dt.timedelta(minutes=dashboard_minutes)
        ).strftime("%Y-%m-%dT%H:%M:00%z")
        with self.connect() as connection:
            files = {
                row["status"]: row["count"]
                for row in connection.execute(
                    "SELECT status,COUNT(*) count FROM files GROUP BY status"
                )
            }
            latest = connection.execute(
                "SELECT MAX(max_event_ts) value FROM files WHERE status='done'"
            ).fetchone()["value"]
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(rows),0) rows,
                       COALESCE(SUM(rejected_rows),0) rejected_rows
                  FROM files WHERE status='done'
                """
            ).fetchone()
            targets = [GLOBAL_TARGET, *[
                row["target"] for row in connection.execute(
                    "SELECT DISTINCT target FROM minute_metrics WHERE target<>? ORDER BY target",
                    (GLOBAL_TARGET,),
                )
            ]]
            def distinct_counts(table: str, key_column: str) -> dict[str, int]:
                return {
                    row["target"]: int(row["identifiers"])
                    for row in connection.execute(
                        f"""
                        SELECT target,COUNT(DISTINCT {key_column}) identifiers
                          FROM {table}
                         WHERE minute_ist>=?
                         GROUP BY target
                        """,
                        (cutoff,),
                    )
                }

            unique_cliips = distinct_counts("minute_viewers", "viewer_key")
            unique_devices = distinct_counts("minute_devices", "device_key")
            unique_sessions = distinct_counts("minute_sessions", "session_key")
            series: dict[str, list[dict]] = {}
            for target in targets:
                metric_rows = connection.execute(
                    """
                    SELECT minute_ist,SUM(requests) requests,SUM(bytes) bytes,
                           SUM(errors_4xx) errors_4xx,SUM(errors_5xx) errors_5xx,
                           SUM(media_segments) media_segments
                      FROM minute_metrics
                     WHERE target=? AND minute_ist>=?
                     GROUP BY minute_ist ORDER BY minute_ist
                    """,
                    (target, cutoff),
                ).fetchall()
                viewer_counts = {
                    row["minute_ist"]: row["viewers"]
                    for row in connection.execute(
                        """
                        SELECT minute_ist,COUNT(DISTINCT viewer_key) viewers
                          FROM minute_viewers
                         WHERE target=? AND minute_ist>=?
                         GROUP BY minute_ist
                        """,
                        (target, cutoff),
                    )
                }
                device_counts = {
                    row["minute_ist"]: row["identifiers"]
                    for row in connection.execute(
                        """
                        SELECT minute_ist,COUNT(DISTINCT device_key) identifiers
                          FROM minute_devices
                         WHERE target=? AND minute_ist>=?
                         GROUP BY minute_ist
                        """,
                        (target, cutoff),
                    )
                }
                session_counts = {
                    row["minute_ist"]: row["identifiers"]
                    for row in connection.execute(
                        """
                        SELECT minute_ist,COUNT(DISTINCT session_key) identifiers
                          FROM minute_sessions
                         WHERE target=? AND minute_ist>=?
                         GROUP BY minute_ist
                        """,
                        (target, cutoff),
                    )
                }
                series[target] = [
                    {
                        **dict(row),
                        "active_cliips": viewer_counts.get(row["minute_ist"], 0),
                        "device_ids": device_counts.get(row["minute_ist"], 0),
                        "session_ids": session_counts.get(row["minute_ist"], 0),
                    }
                    for row in metric_rows
                ]
            summaries = {}
            for target, rows in series.items():
                requests = sum(int(row["requests"]) for row in rows)
                byte_count = sum(int(row["bytes"]) for row in rows)
                segments = sum(int(row["media_segments"]) for row in rows)
                viewers = unique_cliips.get(target, 0)
                watch_seconds = segments * 6
                summaries[target] = {
                    "requests": requests,
                    "bytes": byte_count,
                    "errors_4xx": sum(int(row["errors_4xx"]) for row in rows),
                    "errors_5xx": sum(int(row["errors_5xx"]) for row in rows),
                    "media_segments": segments,
                    "estimated_watch_seconds": watch_seconds,
                    "unique_cliips": viewers,
                    "unique_device_ids": unique_devices.get(target, 0),
                    "unique_session_ids": unique_sessions.get(target, 0),
                    "average_watch_seconds_per_ip": (
                        watch_seconds / viewers if viewers else 0
                    ),
                }
            breakdowns: dict[str, dict[str, list[dict]]] = {}
            dimension_rows = connection.execute(
                """
                SELECT target,dimension,value,SUM(requests) requests,SUM(bytes) bytes
                  FROM minute_dimensions
                 WHERE minute_ist>=?
                 GROUP BY target,dimension,value
                """,
                (cutoff,),
            ).fetchall()
            for row in dimension_rows:
                target_dimensions = breakdowns.setdefault(row["target"], {})
                target_dimensions.setdefault(row["dimension"], []).append({
                    "value": row["value"],
                    "requests": int(row["requests"]),
                    "bytes": int(row["bytes"]),
                })
            for target_dimensions in breakdowns.values():
                for dimension, rows in target_dimensions.items():
                    target_dimensions[dimension] = sorted(
                        rows, key=lambda row: (-row["requests"], row["value"])
                    )[:8]
            events = [
                dict(row) for row in connection.execute(
                    """
                    SELECT occurred_at,level,component,message FROM runtime_events
                    ORDER BY occurred_at DESC LIMIT 20
                    """
                )
            ]
        return {
            "files": files,
            "rows": int(totals["rows"]),
            "rejected_rows": int(totals["rejected_rows"]),
            "latest_event_ts": latest,
            "series": series,
            "summaries": summaries,
            "breakdowns": breakdowns,
            "events": events,
        }
