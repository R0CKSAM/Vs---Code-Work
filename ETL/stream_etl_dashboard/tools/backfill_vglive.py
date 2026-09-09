"""One-time repair for files processed before the vglive source alias existed."""
from __future__ import annotations

import concurrent.futures
import time
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.db import connect, set_status, transaction
from app.transform import parse_file
from app.worker import IST, load_result


DISPLAY_STREAM = "vglive-274906"


def parse(path_text: str, target_date: str):
    path = Path(path_text)
    started = time.monotonic()
    result = parse_file(
        path,
        (DISPLAY_STREAM,),
        target_date,
        settings.stream_aliases,
    )
    return path, result, int((time.monotonic() - started) * 1000)


def main() -> None:
    with connect() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM minute_clients WHERE stream=?", (DISPLAY_STREAM,)
        ).fetchone()[0]
        paths = [
            row[0] for row in conn.execute(
                "SELECT object_key FROM ingested_objects WHERE status='completed' ORDER BY processed_at"
            ) if Path(row[0]).exists()
        ]
    if existing:
        print(f"{DISPLAY_STREAM} already has {existing} rows; backfill skipped.")
        return
    target_date = datetime.now(IST).date().isoformat()
    print(f"Backfilling {DISPLAY_STREAM} from {len(paths)} previously processed files...")
    matched = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.parser_workers) as pool:
        futures = [pool.submit(parse, path, target_date) for path in paths]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            path, result, elapsed = future.result()
            matched += result[3]
            load_result(path, result, elapsed)
            if index % 250 == 0:
                print(f"  {index}/{len(paths)} files")
    with transaction() as conn:
        set_status(conn, "vglive_alias_backfilled", datetime.now(IST).isoformat())
    print(f"Backfill complete: {matched} matching records loaded.")


if __name__ == "__main__":
    main()
