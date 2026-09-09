from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings
from .db import connect, initialize, set_status, transaction
from .transform import parse_file


IST = timezone(timedelta(hours=5, minutes=30))
STOP = threading.Event()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("stream-etl")


def today_paths() -> tuple[str, Path, str]:
    now = datetime.now(IST)
    date = now.date().isoformat()
    remote = f"{settings.rclone_remote}/{now:%m}/{now:%d}"
    local = settings.local_log_root / f"{now:%m-%d-%Y}"
    return remote, local, date


def sync_once() -> None:
    remote, local, _ = today_paths()
    local.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with transaction() as conn:
        set_status(conn, "sync_status", "Syncing")
    result = subprocess.run(
        [settings.rclone_exe, "copy", remote, str(local), "--size-only", "--fast-list",
         "--transfers", "16", "--checkers", "64"],
        capture_output=True, text=True, timeout=180,
    )
    duration = round(time.monotonic() - started, 3)
    with transaction() as conn:
        set_status(conn, "last_sync_seconds", duration)
        set_status(conn, "last_sync_at", datetime.now(IST).isoformat())
        set_status(conn, "sync_status", "Idle" if result.returncode == 0 else "Error")
        if result.returncode:
            set_status(conn, "last_error", result.stderr[-1000:])
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])


def is_pending(path: Path) -> bool:
    stat = path.stat()
    with connect() as conn:
        row = conn.execute(
            "SELECT size_bytes, modified_ns, status FROM ingested_objects WHERE object_key=?",
            (str(path),),
        ).fetchone()
    return not row or row[0] != stat.st_size or row[1] != stat.st_mtime_ns or row[2] != "completed"


def load_result(path: Path, result, elapsed_ms: int) -> None:
    aggregates, errors_4xx, errors_5xx, records, skipped, latest = result
    stat = path.stat()
    with transaction() as conn:
        for key, requests in aggregates.items():
            conn.execute(
                """INSERT INTO minute_clients
                   (minute,stream,client_ip,state,requests,errors_4xx,errors_5xx)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(minute,stream,client_ip,state) DO UPDATE SET
                     requests=requests+excluded.requests,
                     errors_4xx=errors_4xx+excluded.errors_4xx,
                     errors_5xx=errors_5xx+excluded.errors_5xx""",
                (*key, requests, errors_4xx[key], errors_5xx[key]),
            )
        conn.execute(
            """INSERT INTO ingested_objects
               (object_key,size_bytes,modified_ns,status,records_loaded,processing_ms,error_message,processed_at)
               VALUES (?,?,?,?,?,?,NULL,?)
               ON CONFLICT(object_key) DO UPDATE SET size_bytes=excluded.size_bytes,
               modified_ns=excluded.modified_ns,status='completed',records_loaded=excluded.records_loaded,
               processing_ms=excluded.processing_ms,error_message=NULL,processed_at=excluded.processed_at""",
            (str(path), stat.st_size, stat.st_mtime_ns, "completed", records, elapsed_ms,
             datetime.now(IST).isoformat()),
        )
        set_status(conn, "last_scan_at", datetime.now(IST).isoformat())
        set_status(conn, "last_skipped_lines", skipped)
        if latest:
            # Backlog files can finish after newer files. Never let the
            # dashboard watermark move backwards when that happens.
            current = conn.execute(
                "SELECT value FROM pipeline_status WHERE key='latest_event_at'"
            ).fetchone()
            current_dt = None
            if current:
                try:
                    current_dt = datetime.fromisoformat(current[0])
                except (TypeError, ValueError):
                    pass
            if current_dt is None or latest > current_dt:
                set_status(conn, "latest_event_at", latest.isoformat())


def mark_failed(path: Path, error: Exception, elapsed_ms: int) -> None:
    stat = path.stat()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO ingested_objects
               (object_key,size_bytes,modified_ns,status,processing_ms,error_message,processed_at)
               VALUES (?,?,?,?,?,?,?) ON CONFLICT(object_key) DO UPDATE SET
               status='failed',processing_ms=excluded.processing_ms,
               error_message=excluded.error_message,processed_at=excluded.processed_at""",
            (str(path), stat.st_size, stat.st_mtime_ns, "failed", elapsed_ms, str(error)[:1000],
             datetime.now(IST).isoformat()),
        )


def process_path(path: Path, target_date: str):
    started = time.monotonic()
    try:
        return path, parse_file(
            path, settings.streams, target_date, settings.stream_aliases
        ), int((time.monotonic()-started)*1000), None
    except Exception as exc:
        return path, None, int((time.monotonic()-started)*1000), exc


def scan_once() -> int:
    _, local, target_date = today_paths()
    if not local.exists():
        return 0
    candidates = [p for p in local.rglob("*.gz") if p.stat().st_size > 0 and is_pending(p)]
    if not candidates:
        with transaction() as conn:
            set_status(conn, "last_scan_at", datetime.now(IST).isoformat())
            set_status(conn, "queue_depth", 0)
        return 0
    with transaction() as conn:
        set_status(conn, "queue_depth", len(candidates))
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.parser_workers) as pool:
        for path, result, elapsed, error in pool.map(lambda p: process_path(p, target_date), candidates):
            if error:
                logger.error("Failed %s: %s", path, error)
                mark_failed(path, error, elapsed)
            else:
                load_result(path, result, elapsed)
    return len(candidates)


def run(no_sync: bool = False, once: bool = False) -> None:
    initialize()
    logger.info("Database: %s", settings.db_path)
    logger.info("Streams: %s", ", ".join(settings.streams))
    next_sync = 0.0
    while not STOP.is_set():
        now = time.monotonic()
        if not no_sync and now >= next_sync:
            try:
                sync_once()
            except Exception as exc:
                logger.error("Sync failed: %s", exc)
            next_sync = time.monotonic() + settings.sync_interval_seconds
        count = scan_once()
        logger.info("Processed %d candidate files", count)
        if once:
            return
        STOP.wait(settings.scan_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sync", action="store_true", help="Process local logs without rclone")
    parser.add_argument("--once", action="store_true", help="Run one sync/scan cycle")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    run(args.no_sync, args.once)


if __name__ == "__main__":
    main()
