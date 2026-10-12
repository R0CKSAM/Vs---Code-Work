"""
scripts/e2e_step6b_runner.py – Production Validation Runner for Step 6B.

Supports:
  --snapshot-only : Perform READ-ONLY database snapshot & schema audit without running monitor.
  --execute       : Perform controlled production validation (Pre-snapshot -> 1 Run -> Post-snapshot).
  --help          : Show CLI options.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.config.validation import assert_valid_settings
from app.database.connection import init_db
from app.monitor.models import ExitCode, PipelineStatus
from app.monitor.runner import MonitorRunner
from app.observability.logging_config import configure_logging

DB_PATH = ROOT / "data" / "fancode.db"
OUTPUT_FILE = ROOT / "data" / "step6b_validation_result.json"


def to_json_safe(obj: Any) -> Any:
    """Recursively convert any SQLite Row, datetime, or custom objects to JSON-serializable primitives."""
    if isinstance(obj, sqlite3.Row):
        return dict(obj)
    elif isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [to_json_safe(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, "to_dict") and callable(obj.to_dict):
        return to_json_safe(obj.to_dict())
    return obj


def capture_db_snapshot(label: str = "SNAPSHOT") -> dict:
    """
    Read-only inspection of production database using verified table and column schema.
    Zero mutations are performed. All return values are JSON-serializable.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Integrity check (extract strings from Row objects)
    cur.execute("PRAGMA integrity_check;")
    integrity_rows = cur.fetchall()
    integrity_raw = [r[0] if isinstance(r, (sqlite3.Row, tuple, list)) else str(r) for r in integrity_rows]
    integrity_ok = len(integrity_raw) == 1 and integrity_raw[0] == "ok"

    # 2. Foreign key check
    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = [dict(r) for r in cur.fetchall()]

    # 3. Table counts
    tables = [
        "sports", "tours", "matches", "videos", "pages",
        "change_events", "scrape_runs", "notification_batches",
        "notification_deliveries", "notification_event_links"
    ]
    counts = {}
    for t in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t};")
            counts[t] = cur.fetchone()[0]
        except Exception:
            counts[t] = -1

    # 4. Match external_id metrics
    cur.execute("SELECT COUNT(*) FROM matches WHERE external_id IS NULL;")
    null_external_ids = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT external_id) FROM matches WHERE external_id IS NOT NULL;")
    distinct_external_ids = cur.fetchone()[0]

    cur.execute("""
        SELECT external_id, COUNT(*) as cnt
        FROM matches
        WHERE external_id IS NOT NULL
        GROUP BY external_id
        HAVING cnt > 1;
    """)
    duplicates = [dict(r) for r in cur.fetchall()]

    # 5. Match ID 17 and Match by external_id 4249664
    cur.execute(
        "SELECT id, external_id, title, slug, source_url, status, score_summary "
        "FROM matches WHERE id = 17;"
    )
    match_id_17 = [dict(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT id, external_id, title, slug, source_url, status, score_summary "
        "FROM matches WHERE external_id = '4249664';"
    )
    match_4249664 = [dict(r) for r in cur.fetchall()]

    # 6. All matches
    cur.execute(
        "SELECT id, external_id, title, slug, source_url, status, score_summary "
        "FROM matches ORDER BY id ASC;"
    )
    all_matches = [dict(r) for r in cur.fetchall()]

    # 7. Recent scrape runs (using actual ScrapeRun schema columns)
    cur.execute(
        "SELECT id, run_type, started_at, finished_at, status, "
        "records_processed, records_created, records_updated, "
        "changes_detected, errors_count, error_message "
        "FROM scrape_runs ORDER BY id DESC LIMIT 10;"
    )
    recent_runs = [dict(r) for r in cur.fetchall()]

    # 8. Recent change events (using actual ChangeEvent schema columns)
    cur.execute(
        "SELECT id, entity_type, entity_id, external_id, change_type, "
        "field_name, old_value, new_value, severity, scrape_run_id, "
        "detected_at, notified_at "
        "FROM change_events ORDER BY id DESC LIMIT 20;"
    )
    recent_change_events = [dict(r) for r in cur.fetchall()]

    # 9. Recent notification batches
    cur.execute(
        "SELECT id, batch_key, subject, status, event_count, recipient_count, sent_at, error_message, created_at "
        "FROM notification_batches ORDER BY id DESC LIMIT 5;"
    )
    recent_notification_batches = [dict(r) for r in cur.fetchall()]

    # 10. Recent notification deliveries
    cur.execute(
        "SELECT id, batch_id, recipient, status, provider, attempted_at, sent_at, error_message "
        "FROM notification_deliveries ORDER BY id DESC LIMIT 5;"
    )
    recent_deliveries = [dict(r) for r in cur.fetchall()]

    # 11. Recent notification event links
    cur.execute(
        "SELECT id, batch_id, change_event_id "
        "FROM notification_event_links ORDER BY id DESC LIMIT 5;"
    )
    recent_event_links = [dict(r) for r in cur.fetchall()]

    conn.close()

    raw_dict = {
        "label": label,
        "integrity_ok": integrity_ok,
        "integrity_raw": integrity_raw,
        "fk_violations": fk_violations,
        "counts": counts,
        "null_external_ids": null_external_ids,
        "distinct_external_ids": distinct_external_ids,
        "duplicate_external_ids": duplicates,
        "match_id_17": match_id_17,
        "match_4249664": match_4249664,
        "all_matches": all_matches,
        "recent_runs": recent_runs,
        "recent_change_events": recent_change_events,
        "recent_notification_batches": recent_notification_batches,
        "recent_deliveries": recent_deliveries,
        "recent_event_links": recent_event_links,
    }

    return to_json_safe(raw_dict)


def print_snapshot_report(snapshot: dict) -> None:
    print(f"\n[{snapshot['label']} SNAPSHOT REPORT]")
    print(f"  Database Path           : {DB_PATH}")
    print(f"  PRAGMA integrity_check  : {'PASS (ok)' if snapshot['integrity_ok'] else 'FAIL'}")
    print(f"  Foreign Key Violations  : {len(snapshot['fk_violations'])}")
    print(f"  Matches Total           : {snapshot['counts'].get('matches')}")
    print(f"  Null external_id        : {snapshot['null_external_ids']}")
    print(f"  Distinct external_id    : {snapshot['distinct_external_ids']}")
    print(f"  Duplicate external_id   : {len(snapshot['duplicate_external_ids'])}")
    print(f"  Sports Count            : {snapshot['counts'].get('sports')}")
    print(f"  Tours Count             : {snapshot['counts'].get('tours')}")
    print(f"  Videos Count            : {snapshot['counts'].get('videos')}")
    print(f"  Pages Count             : {snapshot['counts'].get('pages')}")
    print(f"  Change Events Total     : {snapshot['counts'].get('change_events')}")
    print(f"  Scrape Runs Total       : {snapshot['counts'].get('scrape_runs')}")
    print(f"  Notification Batches    : {snapshot['counts'].get('notification_batches')}")
    print(f"  Notification Deliveries : {snapshot['counts'].get('notification_deliveries')}")
    print(f"  Notification Event Links: {snapshot['counts'].get('notification_event_links')}")
    print()
    print("  Match ID 17 (by Primary Key):")
    if snapshot.get("match_id_17"):
        for m in snapshot["match_id_17"]:
            print(f"    - ID={m['id']}, ExtID={m['external_id']}, Title={m['title']!r}, Status={m['status']!r}, Score={m['score_summary']!r}")
    else:
        print("    [WARNING] Match ID 17 not found in DB!")
    print()
    print("  Match by external_id = '4249664':")
    if snapshot.get("match_4249664"):
        for m in snapshot["match_4249664"]:
            print(f"    - ID={m['id']}, ExtID={m['external_id']}, Title={m['title']!r}, Status={m['status']!r}, Score={m['score_summary']!r}")
    else:
        print("    [INFO] No match record found with external_id = '4249664'.")
    print()
    print(f"  All Matches in Database ({len(snapshot.get('all_matches', []))} Rows):")
    print("  " + "-" * 90)
    print(f"  {'ID':<4} | {'Ext ID':<8} | {'Title':<30} | {'Slug':<25} | {'Source URL'}")
    print("  " + "-" * 90)
    for m in snapshot.get("all_matches", []):
        print(f"  {m['id']:<4} | {str(m['external_id']):<8} | {m['title'][:30]:<30} | {m['slug'][:25]:<25} | {m['source_url']}")
    print("  " + "-" * 90)
    print()
    print("  Recent Scrape Runs (Top 5):")
    for r in snapshot["recent_runs"][:5]:
        print(f"    - Run #{r['id']}: type={r['run_type']}, status={r['status']}, processed={r['records_processed']}, created={r['records_created']}, updated={r['records_updated']}, changes={r['changes_detected']}, errors={r['errors_count']}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 6B Controlled Production Validation Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Perform read-only database snapshot inspection without running monitor",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute the controlled single production monitor run with pre/post snapshots",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 80)
    print("FANCODE MONITOR — STEP 6B VALIDATION RUNNER")
    print("=" * 80)

    # 1. Snapshot-only mode (Zero mutations, Zero monitor runs)
    if args.snapshot_only or (not args.execute and not args.snapshot_only):
        if not args.execute and not args.snapshot_only:
            # Default to safe snapshot-only if no action explicitly requested
            print("[INFO] No mode specified; defaulting to safe --snapshot-only mode.\n")
        snapshot = capture_db_snapshot("READ_ONLY_INSPECTION")
        print_snapshot_report(snapshot)
        print("=" * 80)
        print("SNAPSHOT-ONLY INSPECTION COMPLETE — ZERO MUTATIONS, ZERO RUNS EXECUTED.")
        print("To execute the single controlled production monitor run, supply: --execute")
        print("=" * 80 + "\n")
        return 0

    # 2. Execution mode (--execute)
    print("\n--- PHASE 1: PRE-RUN SNAPSHOT ---")
    pre_snapshot = capture_db_snapshot("PRE_RUN")
    print_snapshot_report(pre_snapshot)

    # In-memory logging capture
    log_stream = []
    class MemoryLogHandler(logging.Handler):
        def emit(self, record):
            msg = self.format(record)
            log_stream.append(msg)

    mem_handler = MemoryLogHandler()
    mem_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(mem_handler)

    configure_logging(level="INFO", structured_json=False)
    assert_valid_settings()
    init_db()

    print("=" * 80)
    print("--- PHASE 2: EXECUTING EXACTLY ONE PRODUCTION MONITOR RUN ---")
    print("=" * 80 + "\n")

    runner = MonitorRunner()
    run_result = runner.run_once(
        trigger_type="manual",
        dry_run=False,
        skip_discovery=True,
        skip_notifications=False,
        stage_filter=None,
        headed=False,
    )

    print("\n" + "=" * 80)
    print(f"RUN COMPLETE — Status: {run_result.status.value}, Duration: {round(run_result.duration_seconds, 2)}s")
    print("=" * 80)
    result_dict = run_result.to_dict()
    print(json.dumps(result_dict, indent=2, default=str))

    print("\n--- PHASE 3: POST-RUN SNAPSHOT ---")
    post_snapshot = capture_db_snapshot("POST_RUN")
    print_snapshot_report(post_snapshot)

    # Compute deltas
    pre_event_count = pre_snapshot['counts'].get('change_events', 0)
    post_event_count = post_snapshot['counts'].get('change_events', 0)
    new_event_count = max(0, post_event_count - pre_event_count)
    new_events = []
    if new_event_count > 0:
        new_events = post_snapshot['recent_change_events'][:new_event_count]

    full_output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pre_snapshot": pre_snapshot,
        "run_result": result_dict,
        "post_snapshot": post_snapshot,
        "new_change_events": new_events,
        "logs": log_stream,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(to_json_safe(full_output), f, indent=2, default=str)

    print(f"\nSaved complete validation report to {OUTPUT_FILE}")
    print("=" * 80)
    print(f"STEP 6B VALIDATION FINISHED — EXIT CODE: {run_result.exit_code}")
    print("=" * 80 + "\n")

    return int(run_result.exit_code)


if __name__ == "__main__":
    sys.exit(main())
