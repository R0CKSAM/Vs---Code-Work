from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterator

from .parser import DAVIS_CUP_ALIASES, FileBatch, GLOBAL_TARGET, IST


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
    ttfb_samples INTEGER NOT NULL DEFAULT 0,
    ttfb_total_ms REAL NOT NULL DEFAULT 0,
    turnaround_samples INTEGER NOT NULL DEFAULT 0,
    turnaround_total_ms REAL NOT NULL DEFAULT 0,
    transfer_samples INTEGER NOT NULL DEFAULT 0,
    transfer_total_ms REAL NOT NULL DEFAULT 0,
    throughput_samples INTEGER NOT NULL DEFAULT 0,
    throughput_total REAL NOT NULL DEFAULT 0,
    tls_overhead_samples INTEGER NOT NULL DEFAULT 0,
    tls_overhead_total_ms REAL NOT NULL DEFAULT 0,
    delivery_edge_issues INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS minute_quality_dimensions (
    minute_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    requests INTEGER NOT NULL,
    errors_4xx INTEGER NOT NULL,
    errors_5xx INTEGER NOT NULL,
    ttfb_samples INTEGER NOT NULL,
    ttfb_total_ms REAL NOT NULL,
    turnaround_samples INTEGER NOT NULL,
    turnaround_total_ms REAL NOT NULL,
    throughput_samples INTEGER NOT NULL,
    throughput_total REAL NOT NULL,
    PRIMARY KEY(minute_ist, req_host, target, dimension, value)
);
CREATE INDEX IF NOT EXISTS minute_quality_dimensions_target_idx
    ON minute_quality_dimensions(target, dimension, minute_ist);
CREATE TABLE IF NOT EXISTS daily_viewers (
    date_ist TEXT NOT NULL,
    req_host TEXT NOT NULL,
    target TEXT NOT NULL,
    viewer_key TEXT NOT NULL,
    PRIMARY KEY(date_ist, req_host, target, viewer_key)
);
CREATE INDEX IF NOT EXISTS daily_viewers_target_idx
    ON daily_viewers(target, date_ist);
CREATE TABLE IF NOT EXISTS viewer_history (
    target TEXT NOT NULL,
    viewer_key TEXT NOT NULL,
    first_seen_ist TEXT NOT NULL,
    last_seen_ist TEXT NOT NULL,
    PRIMARY KEY(target, viewer_key)
);
CREATE INDEX IF NOT EXISTS viewer_history_last_seen_idx
    ON viewer_history(target, last_seen_ist);
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
        self._writer_lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_metric_columns(connection)
            self._migrate_dimension_labels(connection)
            self._bootstrap_viewer_history(connection)

    @staticmethod
    def _ensure_metric_columns(connection: sqlite3.Connection) -> None:
        """Upgrade existing live databases in place without dropping audience data."""
        existing = {
            row[1] for row in connection.execute("PRAGMA table_info(minute_metrics)")
        }
        columns = {
            "ttfb_samples": "INTEGER NOT NULL DEFAULT 0",
            "ttfb_total_ms": "REAL NOT NULL DEFAULT 0",
            "turnaround_samples": "INTEGER NOT NULL DEFAULT 0",
            "turnaround_total_ms": "REAL NOT NULL DEFAULT 0",
            "transfer_samples": "INTEGER NOT NULL DEFAULT 0",
            "transfer_total_ms": "REAL NOT NULL DEFAULT 0",
            "throughput_samples": "INTEGER NOT NULL DEFAULT 0",
            "throughput_total": "REAL NOT NULL DEFAULT 0",
            "tls_overhead_samples": "INTEGER NOT NULL DEFAULT 0",
            "tls_overhead_total_ms": "REAL NOT NULL DEFAULT 0",
            "delivery_edge_issues": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, declaration in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE minute_metrics ADD COLUMN {name} {declaration}"
                )

    @staticmethod
    def _migrate_dimension_labels(connection: sqlite3.Connection) -> None:
        """Merge legacy numeric/CDN labels into their documented display labels."""
        migration_key = "dimension_labels_v2"
        migrated = connection.execute(
            "SELECT value FROM metadata WHERE key=?", (migration_key,)
        ).fetchone()
        if migrated:
            return
        mappings = (
            ("cache", "Miss", "Non-cacheable"),
            ("cache", "Hit", "Cache hit - child edge"),
            ("delivery_type", "0", "Default"),
            ("delivery_type", "1", "Adaptive media - live"),
            ("delivery_type", "2", "Adaptive media - VOD"),
            ("delivery_type", "3", "Download delivery"),
            ("delivery_format", "0", "Default"),
            ("delivery_format", "1", "Apple / HLS"),
            ("delivery_format", "2", "ZERI"),
            ("delivery_format", "3", "Silverlight"),
            ("delivery_format", "4", "DASH"),
            ("media_encryption", "0", "Disabled"),
            ("media_encryption", "1", "Enabled"),
        )
        for dimension, old_value, new_value in mappings:
            connection.execute(
                """
                INSERT INTO minute_dimensions(
                    minute_ist,req_host,target,dimension,value,requests,bytes
                )
                SELECT minute_ist,req_host,target,dimension,?,requests,bytes
                  FROM minute_dimensions
                 WHERE dimension=? AND value=?
                ON CONFLICT(minute_ist,req_host,target,dimension,value) DO UPDATE SET
                    requests=requests+excluded.requests,
                    bytes=bytes+excluded.bytes
                """,
                (new_value, dimension, old_value),
            )
            connection.execute(
                "DELETE FROM minute_dimensions WHERE dimension=? AND value=?",
                (dimension, old_value),
            )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?)", (migration_key, "complete")
        )

    @staticmethod
    def _bootstrap_viewer_history(connection: sqlite3.Connection) -> None:
        """Seed durable first/last-seen state from identities already processed."""
        migration_key = "viewer_history_v1"
        migrated = connection.execute(
            "SELECT value FROM metadata WHERE key=?", (migration_key,)
        ).fetchone()
        if migrated:
            return
        connection.execute(
            """
            INSERT INTO viewer_history(target,viewer_key,first_seen_ist,last_seen_ist)
            SELECT target,viewer_key,MIN(minute_ist),MAX(minute_ist)
              FROM minute_viewers
             GROUP BY target,viewer_key
            ON CONFLICT(target,viewer_key) DO UPDATE SET
                first_seen_ist=MIN(first_seen_ist,excluded.first_seen_ist),
                last_seen_ist=MAX(last_seen_ist,excluded.last_seen_ist)
            """
        )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?)", (migration_key, "complete")
        )

    @contextlib.contextmanager
    def connect(self, write: bool = True) -> Iterator[sqlite3.Connection]:
        # SQLite has one writer. Queue our workers instead of racing its timeout.
        if write:
            self._writer_lock.acquire()
        try:
            with self._connection() as connection:
                yield connection
        finally:
            if write:
                self._writer_lock.release()

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        # This is connection-local; setting it only during schema creation left
        # every subsequent small write at SQLite's more expensive default.
        connection.execute("PRAGMA synchronous=NORMAL")
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
            connection.execute("DELETE FROM minute_quality_dimensions")
            connection.execute("DELETE FROM daily_viewers")
            connection.execute("DELETE FROM viewer_history")
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
        with self.connect(write=False) as connection:
            rows = connection.execute(
                "SELECT path,size,mtime_ns FROM files WHERE status <> 'observed'"
            )
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
            connection.execute("BEGIN IMMEDIATE")
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
                    media_segments,ttfb_samples,ttfb_total_ms,turnaround_samples,
                    turnaround_total_ms,transfer_samples,transfer_total_ms,
                    throughput_samples,throughput_total,tls_overhead_samples,
                    tls_overhead_total_ms,delivery_edge_issues
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(minute_ist,req_host,target) DO UPDATE SET
                    requests=requests+excluded.requests,
                    bytes=bytes+excluded.bytes,
                    errors_4xx=errors_4xx+excluded.errors_4xx,
                    errors_5xx=errors_5xx+excluded.errors_5xx,
                    media_segments=media_segments+excluded.media_segments,
                    ttfb_samples=ttfb_samples+excluded.ttfb_samples,
                    ttfb_total_ms=ttfb_total_ms+excluded.ttfb_total_ms,
                    turnaround_samples=turnaround_samples+excluded.turnaround_samples,
                    turnaround_total_ms=turnaround_total_ms+excluded.turnaround_total_ms,
                    transfer_samples=transfer_samples+excluded.transfer_samples,
                    transfer_total_ms=transfer_total_ms+excluded.transfer_total_ms,
                    throughput_samples=throughput_samples+excluded.throughput_samples,
                    throughput_total=throughput_total+excluded.throughput_total,
                    tls_overhead_samples=tls_overhead_samples+excluded.tls_overhead_samples,
                    tls_overhead_total_ms=tls_overhead_total_ms+excluded.tls_overhead_total_ms,
                    delivery_edge_issues=delivery_edge_issues+excluded.delivery_edge_issues
                """,
                [(*key, *values) for key, values in batch.metrics.items()],
            )
            connection.executemany(
                "INSERT OR IGNORE INTO minute_viewers VALUES(?,?,?,?)",
                batch.minute_viewers,
            )
            viewer_history: dict[tuple[str, str], list[str]] = {}
            for minute_ist, _req_host, target, viewer_key in batch.minute_viewers:
                bounds = viewer_history.setdefault(
                    (target, viewer_key), [minute_ist, minute_ist]
                )
                bounds[0] = min(bounds[0], minute_ist)
                bounds[1] = max(bounds[1], minute_ist)
            connection.executemany(
                """
                INSERT INTO viewer_history(
                    target,viewer_key,first_seen_ist,last_seen_ist
                ) VALUES(?,?,?,?)
                ON CONFLICT(target,viewer_key) DO UPDATE SET
                    first_seen_ist=MIN(first_seen_ist,excluded.first_seen_ist),
                    last_seen_ist=MAX(last_seen_ist,excluded.last_seen_ist)
                """,
                [(*key, *bounds) for key, bounds in viewer_history.items()],
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
                """
                INSERT INTO minute_quality_dimensions(
                    minute_ist,req_host,target,dimension,value,requests,
                    errors_4xx,errors_5xx,ttfb_samples,ttfb_total_ms,
                    turnaround_samples,turnaround_total_ms,
                    throughput_samples,throughput_total
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(minute_ist,req_host,target,dimension,value) DO UPDATE SET
                    requests=requests+excluded.requests,
                    errors_4xx=errors_4xx+excluded.errors_4xx,
                    errors_5xx=errors_5xx+excluded.errors_5xx,
                    ttfb_samples=ttfb_samples+excluded.ttfb_samples,
                    ttfb_total_ms=ttfb_total_ms+excluded.ttfb_total_ms,
                    turnaround_samples=turnaround_samples+excluded.turnaround_samples,
                    turnaround_total_ms=turnaround_total_ms+excluded.turnaround_total_ms,
                    throughput_samples=throughput_samples+excluded.throughput_samples,
                    throughput_total=throughput_total+excluded.throughput_total
                """,
                [(*key, *values) for key, values in batch.quality_dimensions.items()],
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

    def snapshot(self, dashboard_minutes: int, selected_targets: list[str] | None = None,
                 *, now: dt.datetime | None = None) -> dict:
        now = (now or dt.datetime.now(IST)).astimezone(IST)
        start = (now - dt.timedelta(minutes=dashboard_minutes) if dashboard_minutes > 0
                 else now.replace(hour=0, minute=0, second=0, microsecond=0))
        cutoff = start.strftime("%Y-%m-%dT%H:%M:00%z")
        end = now.strftime("%Y-%m-%dT%H:%M:00%z")
        with self.connect(write=False) as connection:
            # Pin every query below to one WAL snapshot while parser workers commit.
            connection.execute("BEGIN")
            def literal(value):
                return "'" + str(value).replace("'", "''") + "'"

            canonical = 'CASE target ' + ' '.join(
                f'WHEN {literal(old)} THEN {literal(new)}'
                for old, new in DAVIS_CUP_ALIASES.items()
            ) + ' ELSE target END' if DAVIS_CUP_ALIASES else 'target'
            selected = None if selected_targets is None else {
                DAVIS_CUP_ALIASES.get(target, target) for target in selected_targets
                if target != GLOBAL_TARGET
            }
            raw_selected = set(selected or ())
            raw_selected.update(old for old, new in DAVIS_CUP_ALIASES.items() if new in raw_selected)
            predicate = 'TRUE' if selected is None else (
                f"target IN ({','.join(map(literal, sorted(raw_selected)))})" if selected else 'FALSE'
            )
            projected_target = canonical if selected is None else "'__selection__'"
            # Force the time-leading primary index: the target index otherwise
            # scans all historical identity/dimension rows for an all-target query.
            for table in ('minute_metrics', 'minute_viewers', 'minute_devices',
                          'minute_sessions', 'minute_dimensions', 'minute_quality_dimensions'):
                columns = [row['name'] for row in connection.execute(f'PRAGMA main.table_info({table})')]
                projection = ','.join(f'{projected_target} AS target' if col == 'target' else f'"{col}"' for col in columns)
                index = f'sqlite_autoindex_{table}_1'
                if selected is not None and table in ('minute_viewers', 'minute_devices', 'minute_sessions'):
                    index = f'{table}_target_idx'
                connection.execute(f'''CREATE TEMP VIEW {table} AS SELECT {projection}
                    FROM main.{table} INDEXED BY {index}
                    WHERE minute_ist>={literal(cutoff)} AND minute_ist<={literal(end)}
                      AND ({predicate})''')
            history_index = ('minute_viewers_target_idx' if selected is not None
                             else 'sqlite_autoindex_minute_viewers_1')
            connection.execute(f'''CREATE TEMP VIEW viewer_history AS
                SELECT {projected_target} AS target, viewer_key,
                       MIN(first_seen_ist) first_seen_ist, MAX(last_seen_ist) last_seen_ist
                FROM main.viewer_history WHERE ({predicate}) AND (target,viewer_key) IN (
                    SELECT target,viewer_key FROM main.minute_viewers
                    INDEXED BY {history_index}
                    WHERE minute_ist>={literal(cutoff)} AND minute_ist<={literal(end)}
                      AND ({predicate}))
                GROUP BY 1,2''')
            # Interactive selections need no full-ledger scan (millions of files).
            # Runtime/ingestion metadata comes from the already-published snapshot.
            ledger = connection.execute('''SELECT status,COUNT(*) count,
                COALESCE(SUM(rows),0) rows,COALESCE(SUM(rejected_rows),0) rejected_rows,
                MAX(max_event_ts) latest FROM files NOT INDEXED GROUP BY status''').fetchall() if selected is None else []
            files = {row['status']: row['count'] for row in ledger}
            completed = [row for row in ledger if row['status'] in ('done', 'changed')]
            latest = max((row['latest'] for row in completed if row['latest'] is not None), default=None)
            totals = {key: sum(row[key] for row in completed) for key in ('rows', 'rejected_rows')}
            targets = [GLOBAL_TARGET, *[
                row["target"] for row in connection.execute(
                    "SELECT DISTINCT target FROM minute_metrics WHERE target<>? ORDER BY target",
                    (GLOBAL_TARGET,),
                )
            ]]
            if selected_targets is not None:
                targets = ['__selection__']
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
            viewer_types = {
                row["target"]: {
                    "new": int(row["new_viewers"]),
                    "returning": int(row["returning_viewers"]),
                }
                for row in connection.execute(
                    """
                    SELECT active.target,
                           SUM(CASE WHEN history.first_seen_ist>=? THEN 1 ELSE 0 END)
                               new_viewers,
                           SUM(CASE WHEN history.first_seen_ist<? THEN 1 ELSE 0 END)
                               returning_viewers
                      FROM (
                            SELECT DISTINCT target,viewer_key
                              FROM minute_viewers
                             WHERE minute_ist>=?
                           ) active
                      JOIN viewer_history history
                        ON history.target=active.target
                       AND history.viewer_key=active.viewer_key
                     GROUP BY active.target
                    """,
                    (cutoff, cutoff, cutoff),
                )
            }
            series: dict[str, list[dict]] = {}
            metric_rows_by_target = {}
            for row in connection.execute(
                    """
                    SELECT target,minute_ist,SUM(requests) requests,SUM(bytes) bytes,
                           SUM(errors_4xx) errors_4xx,SUM(errors_5xx) errors_5xx,
                           SUM(media_segments) media_segments,
                           SUM(ttfb_samples) ttfb_samples,SUM(ttfb_total_ms) ttfb_total_ms,
                           SUM(turnaround_samples) turnaround_samples,
                           SUM(turnaround_total_ms) turnaround_total_ms,
                           SUM(transfer_samples) transfer_samples,
                           SUM(transfer_total_ms) transfer_total_ms,
                           SUM(throughput_samples) throughput_samples,
                           SUM(throughput_total) throughput_total,
                           SUM(tls_overhead_samples) tls_overhead_samples,
                           SUM(tls_overhead_total_ms) tls_overhead_total_ms,
                           SUM(delivery_edge_issues) delivery_edge_issues
                      FROM minute_metrics
                     WHERE minute_ist>=?
                     GROUP BY target,minute_ist ORDER BY target,minute_ist
                    """,
                    (cutoff,),
                ):
                metric_rows_by_target.setdefault(row['target'], []).append(row)

            def minute_counts(table, identity):
                counts = {}
                for row in connection.execute(f'''SELECT target,minute_ist,
                    COUNT(DISTINCT {identity}) identifiers FROM {table}
                    WHERE minute_ist>=? GROUP BY target,minute_ist''', (cutoff,)):
                    counts.setdefault(row['target'], {})[row['minute_ist']] = row['identifiers']
                return counts

            all_viewer_counts = minute_counts('minute_viewers', 'viewer_key')
            all_device_counts = minute_counts('minute_devices', 'device_key')
            all_session_counts = minute_counts('minute_sessions', 'session_key')
            for target in targets:
                metric_rows = metric_rows_by_target.get(target, [])
                viewer_counts = all_viewer_counts.get(target, {})
                device_counts = all_device_counts.get(target, {})
                session_counts = all_session_counts.get(target, {})
                series[target] = [
                    {
                        **dict(row),
                        "ttfb_avg_ms": row["ttfb_total_ms"] / row["ttfb_samples"] if row["ttfb_samples"] else None,
                        "turnaround_avg_ms": row["turnaround_total_ms"] / row["turnaround_samples"] if row["turnaround_samples"] else None,
                        "transfer_avg_ms": row["transfer_total_ms"] / row["transfer_samples"] if row["transfer_samples"] else None,
                        "throughput_avg": row["throughput_total"] / row["throughput_samples"] if row["throughput_samples"] else None,
                        "tls_overhead_avg_ms": row["tls_overhead_total_ms"] / row["tls_overhead_samples"] if row["tls_overhead_samples"] else None,
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
                    "new_cliips": viewer_types.get(target, {}).get("new", 0),
                    "returning_cliips": viewer_types.get(target, {}).get(
                        "returning", 0
                    ),
                    "unique_device_ids": unique_devices.get(target, 0),
                    "unique_session_ids": unique_sessions.get(target, 0),
                    "average_watch_seconds_per_ip": (
                        watch_seconds / viewers if viewers else 0
                    ),
                }
                for metric in ("ttfb", "turnaround", "transfer", "tls_overhead"):
                    samples = sum(int(row[f"{metric}_samples"]) for row in rows)
                    total = sum(float(row[f"{metric}_total_ms"]) for row in rows)
                    summaries[target][f"{metric}_samples"] = samples
                    summaries[target][f"{metric}_avg_ms"] = total / samples if samples else None
                throughput_samples = sum(int(row["throughput_samples"]) for row in rows)
                throughput_total = sum(float(row["throughput_total"]) for row in rows)
                summaries[target]["throughput_samples"] = throughput_samples
                summaries[target]["throughput_avg"] = (
                    throughput_total / throughput_samples if throughput_samples else None
                )
                summaries[target]["delivery_edge_issues"] = sum(
                    int(row["delivery_edge_issues"]) for row in rows
                )
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
            quality_rows = connection.execute(
                """
                SELECT target,dimension,value,SUM(requests) quality_requests,
                       SUM(errors_4xx) errors_4xx,SUM(errors_5xx) errors_5xx,
                       SUM(ttfb_samples) ttfb_samples,
                       SUM(ttfb_total_ms) ttfb_total_ms,
                       SUM(turnaround_samples) turnaround_samples,
                       SUM(turnaround_total_ms) turnaround_total_ms,
                       SUM(throughput_samples) throughput_samples,
                       SUM(throughput_total) throughput_total
                  FROM minute_quality_dimensions
                 WHERE minute_ist>=?
                 GROUP BY target,dimension,value
                """,
                (cutoff,),
            ).fetchall()
            for row in quality_rows:
                target_dimensions = breakdowns.setdefault(row["target"], {})
                values = target_dimensions.setdefault(row["dimension"], [])
                item = next(
                    (entry for entry in values if entry["value"] == row["value"]), None
                )
                if item is None:
                    item = {"value": row["value"], "requests": 0, "bytes": 0}
                    values.append(item)
                item.update({
                    "quality_requests": int(row["quality_requests"]),
                    "errors_4xx": int(row["errors_4xx"]),
                    "errors_5xx": int(row["errors_5xx"]),
                    "ttfb_samples": int(row["ttfb_samples"]),
                    "ttfb_avg_ms": (
                        row["ttfb_total_ms"] / row["ttfb_samples"]
                        if row["ttfb_samples"] else None
                    ),
                    "turnaround_samples": int(row["turnaround_samples"]),
                    "turnaround_avg_ms": (
                        row["turnaround_total_ms"] / row["turnaround_samples"]
                        if row["turnaround_samples"] else None
                    ),
                    "throughput_samples": int(row["throughput_samples"]),
                    "throughput_avg": (
                        row["throughput_total"] / row["throughput_samples"]
                        if row["throughput_samples"] else None
                    ),
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
            "window_mode": "rolling" if dashboard_minutes > 0 else "today",
            "window_start_ist": cutoff,
            "window_end_ist": end,
            "window_minutes": int((now.replace(second=0, microsecond=0)
                                    - start.replace(second=0, microsecond=0)).total_seconds() // 60) + 1,
            "files": files,
            "rows": int(totals["rows"]),
            "rejected_rows": int(totals["rejected_rows"]),
            "latest_event_ts": latest,
            "series": series,
            "summaries": summaries,
            "breakdowns": breakdowns,
            "events": events,
        }
