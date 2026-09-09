"""Responsive worker entrypoint: sync and ETL run independently."""
from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import signal
import threading
from datetime import datetime
from pathlib import Path

from . import worker as core
from .config import settings
from .db import connect, initialize, set_status, transaction


logger = logging.getLogger("stream-etl")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))


def find_pending(local: Path) -> list[Path]:
    with connect() as conn:
        completed = {
            row["object_key"]: (row["size_bytes"], row["modified_ns"])
            for row in conn.execute(
                "SELECT object_key,size_bytes,modified_ns FROM ingested_objects WHERE status='completed'"
            )
        }
    candidates: list[tuple[int, Path]] = []
    for path in local.rglob("*.gz"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size and completed.get(str(path)) != (stat.st_size, stat.st_mtime_ns):
            candidates.append((stat.st_mtime_ns, path))
    candidates.sort(reverse=True)
    return [path for _, path in candidates[:BATCH_SIZE]]


def scan_once() -> int:
    _, local, target_date = core.today_paths()
    if not local.exists():
        logger.warning("Local log directory is not available yet: %s", local)
        return 0
    candidates = find_pending(local)
    with transaction() as conn:
        set_status(conn, "queue_depth", len(candidates))
        set_status(conn, "last_scan_at", datetime.now(core.IST).isoformat())
    if not candidates:
        return 0
    logger.info("Processing newest batch of %d files", len(candidates))
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.parser_workers) as pool:
        for path, result, elapsed, error in pool.map(
            lambda p: core.process_path(p, target_date), candidates
        ):
            if error:
                logger.error("Failed %s: %s", path, error)
                core.mark_failed(path, error, elapsed)
            else:
                core.load_result(path, result, elapsed)
    return len(candidates)


def sync_forever() -> None:
    while not core.STOP.is_set():
        try:
            core.sync_once()
        except Exception as exc:
            logger.error("Sync failed: %s", exc)
        core.STOP.wait(settings.sync_interval_seconds)


def run(no_sync: bool, once: bool) -> None:
    initialize()
    logger.info("Database: %s", settings.db_path)
    logger.info("Streams: %s", ", ".join(settings.streams))
    if not no_sync and not once:
        threading.Thread(target=sync_forever, daemon=True, name="RcloneSync").start()
    if not no_sync and once:
        try:
            core.sync_once()
        except Exception as exc:
            logger.error("Sync failed: %s", exc)
    while not core.STOP.is_set():
        count = scan_once()
        logger.info("Processed %d files in this scan", count)
        if once:
            return
        core.STOP.wait(settings.scan_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, lambda *_: core.STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: core.STOP.set())
    run(args.no_sync, args.once)


if __name__ == "__main__":
    main()

