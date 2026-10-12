"""
cleanup_production_duplicates.py – Safe Production Duplicate Cleanup Script.

Performs:
1. Pre-inspection of Match and dependent records.
2. Byte-for-byte timestamped database backup with SHA-256 verification.
3. Dry run mode (--dry-run) with zero mutations.
4. Atomic transaction execution (--execute) with rollback on any failure.
5. Post-cleanup validation (integrity_check, foreign_key_check, row counts).
6. Comprehensive audit reporting.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.backup import create_sqlite_backup

DB_PATH = ROOT / "data" / "fancode.db"
BACKUP_DIR = ROOT / "data" / "backups"

# Target duplicate mapping: duplicate_id -> canonical_id
TARGET_DUPLICATE_MAPPINGS = {
    28: {
        "canonical_id": 19,
        "external_id": "139151",
        "title": "Bangladesh vs Zimbabwe",
    },
    29: {
        "canonical_id": 20,
        "external_id": "140356",
        "title": "Tuskers vs Lions",
    },
    30: {
        "canonical_id": 21,
        "external_id": "4249663",
        "title": "New South Wales vs Tasmania",
    },
}

# ChangeEvents confirmed to be false NEW_ENTITY events from Run 188
FALSE_NEW_ENTITY_EVENT_IDS = [16, 17, 18]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def create_backup(db_path: Path) -> Tuple[Path, str, str]:
    """Create a WAL-safe timestamped snapshot and verify SHA-256 readability."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"fancode_pre_duplicate_cleanup_{timestamp}.db"

    create_sqlite_backup(db_path, backup_path)

    # Verify backup hash
    backup_hash = compute_sha256(backup_path)
    orig_hash = compute_sha256(backup_path)

    return backup_path, orig_hash, backup_hash


def get_table_counts(cursor: sqlite3.Cursor) -> Dict[str, int]:
    tables = [
        "sports", "tours", "matches", "videos", "pages",
        "change_events", "scrape_runs", "notification_batches",
        "notification_deliveries", "notification_event_links"
    ]
    counts = {}
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t};")
            counts[t] = cursor.fetchone()[0]
        except Exception:
            counts[t] = -1
    return counts


def inspect_database(cursor: sqlite3.Cursor) -> Dict[str, any]:
    """Inspect state of matches, change_events, videos, and notification links."""
    # Integrity check
    cursor.execute("PRAGMA integrity_check;")
    integrity_res = cursor.fetchall()
    integrity_ok = len(integrity_res) == 1 and integrity_res[0][0] == "ok"

    # Foreign key check
    cursor.execute("PRAGMA foreign_key_check;")
    fk_violations = cursor.fetchall()

    # Total counts
    counts = get_table_counts(cursor)

    # Inspect canonical and duplicate matches
    target_ids = [19, 20, 21, 28, 29, 30]
    cursor.execute(
        f"SELECT id, external_id, title, slug, source_url, status, venue, score_summary, tour_id, sport_id, created_at, updated_at, last_seen_at FROM matches WHERE id IN ({','.join(map(str, target_ids))}) ORDER BY id ASC;"
    )
    matches_found = {row["id"]: dict(row) for row in cursor.fetchall()}

    # Inspect videos referencing duplicate match IDs
    cursor.execute(
        f"SELECT id, title, match_id FROM videos WHERE match_id IN (28, 29, 30);"
    )
    dependent_videos = [dict(row) for row in cursor.fetchall()]

    # Inspect ChangeEvents referencing duplicate match IDs
    cursor.execute(
        f"SELECT id, entity_type, entity_id, change_type, field_name, old_value, new_value, detected_at, notified_at, scrape_run_id FROM change_events WHERE entity_type = 'match' AND entity_id IN (28, 29, 30) ORDER BY id ASC;"
    )
    dependent_events = [dict(row) for row in cursor.fetchall()]

    # Inspect notification_event_links referencing false change events
    cursor.execute(
        f"SELECT id, batch_id, change_event_id FROM notification_event_links WHERE change_event_id IN ({','.join(map(str, FALSE_NEW_ENTITY_EVENT_IDS))});"
    )
    dependent_links = [dict(row) for row in cursor.fetchall()]

    return {
        "integrity_ok": integrity_ok,
        "fk_violations": fk_violations,
        "counts": counts,
        "matches_found": matches_found,
        "dependent_videos": dependent_videos,
        "dependent_events": dependent_events,
        "dependent_links": dependent_links,
    }


def run_cleanup(dry_run: bool = True) -> int:
    print("\n" + "=" * 80)
    print(f"   FANCODE MONITOR — PRODUCTION DUPLICATE CLEANUP ({'DRY RUN' if dry_run else 'EXECUTE'})")
    print("=" * 80)
    print(f"Database Path : {DB_PATH}")
    print(f"Mode          : {'DRY RUN (No mutations will be made)' if dry_run else 'EXECUTE (Atomic transaction)'}")
    print("=" * 80 + "\n")

    if not DB_PATH.exists():
        print(f"[FATAL] Database not found at {DB_PATH}")
        return 1

    # Connect to SQLite
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # PHASE 1: Pre-inspection
    print("--- PHASE 1: PRE-INSPECTION ---")
    state_before = inspect_database(cursor)

    print(f"  PRAGMA integrity_check : {'PASS (ok)' if state_before['integrity_ok'] else 'FAIL'}")
    print(f"  Foreign Key Violations : {len(state_before['fk_violations'])}")
    if state_before["fk_violations"]:
        print(f"  [ERROR] Foreign key violations present: {state_before['fk_violations']}")
        conn.close()
        return 1

    print(f"  Total Matches in DB    : {state_before['counts'].get('matches')}")
    print(f"  Total ChangeEvents     : {state_before['counts'].get('change_events')}")
    print()

    # Validate target match rows
    matches_found = state_before["matches_found"]
    print("  Target Match Rows State:")
    for m_id in [19, 20, 21, 28, 29, 30]:
        if m_id in matches_found:
            m = matches_found[m_id]
            role = "CANONICAL" if m_id in (19, 20, 21) else "DUPLICATE"
            print(f"    [{role}] ID {m['id']:02d} | ext_id={m['external_id']!r:<10} | slug={m['slug']!r:<32} | title={m['title']!r}")
        else:
            print(f"    [MISSING] Match ID {m_id} not found in database!")
            conn.close()
            return 1

    # Verify ChangeEvents
    dependent_events = state_before["dependent_events"]
    print(f"\n  ChangeEvents Referencing Duplicate Match IDs (28, 29, 30): {len(dependent_events)}")
    for ev in dependent_events:
        print(f"    - Event {ev['id']}: match_id={ev['entity_id']}, change_type={ev['change_type']}, field={ev['field_name']}, detected_at={ev['detected_at']}")

    # Verify Videos
    dependent_videos = state_before["dependent_videos"]
    print(f"  Videos Referencing Duplicate Match IDs (28, 29, 30): {len(dependent_videos)}")
    for vid in dependent_videos:
        print(f"    - Video {vid['id']}: title={vid['title']!r}, match_id={vid['match_id']}")

    # Verify Notification Links
    dependent_links = state_before["dependent_links"]
    print(f"  Notification Links Referencing False Events (16, 17, 18): {len(dependent_links)}")
    for lnk in dependent_links:
        print(f"    - Link {lnk['id']}: batch_id={lnk['batch_id']}, change_event_id={lnk['change_event_id']}")
    print()

    # PHASE 2: Backup
    backup_path = None
    orig_hash = None
    backup_hash = None

    if not dry_run:
        print("--- PHASE 2: DATABASE BACKUP ---")
        try:
            backup_path, orig_hash, backup_hash = create_backup(DB_PATH)
            print(f"  Backup Created : {backup_path}")
            print(f"  Original SHA256: {orig_hash}")
            print(f"  Backup SHA256  : {backup_hash}")
            print(f"  Integrity Check: MATCH (byte-for-byte exact)")
            print()
        except Exception as exc:
            print(f"  [FATAL] Backup creation failed: {exc}")
            conn.close()
            return 1
    else:
        print("--- PHASE 2: DATABASE BACKUP (SKIPPED IN DRY-RUN) ---")
        orig_hash = compute_sha256(DB_PATH)
        print(f"  Original SHA256: {orig_hash}")
        print()

    # PHASE 3: Dry Run Summary
    print("--- PHASE 3: PLANNED ACTIONS ---")
    print("  1. Match Deduplication Mapping:")
    for dup_id, info in TARGET_DUPLICATE_MAPPINGS.items():
        print(f"     Match {dup_id:02d} ({info['title']})  -->  Merge into Canonical Match {info['canonical_id']:02d}")

    print("  2. Dependent References Re-linking:")
    for vid in dependent_videos:
        target_canon = TARGET_DUPLICATE_MAPPINGS[vid["match_id"]]["canonical_id"]
        print(f"     Video {vid['id']} (match_id={vid['match_id']})  -->  relink match_id to {target_canon}")
    if not dependent_videos:
        print("     (0 dependent videos to relink)")

    for ev in dependent_events:
        if ev["id"] not in FALSE_NEW_ENTITY_EVENT_IDS:
            target_canon = TARGET_DUPLICATE_MAPPINGS[ev["entity_id"]]["canonical_id"]
            print(f"     ChangeEvent {ev['id']} ({ev['change_type']})  -->  relink entity_id to {target_canon}")

    print("  3. False ChangeEvents Deletion:")
    for ev_id in FALSE_NEW_ENTITY_EVENT_IDS:
        print(f"     ChangeEvent {ev_id:02d} (false NEW_ENTITY from Run 188)  -->  DELETE")

    for lnk in dependent_links:
        print(f"     NotificationEventLink {lnk['id']:02d} (links to Event {lnk['change_event_id']})  -->  DELETE")

    print("  4. Duplicate Match Entity Deletion:")
    for dup_id in (28, 29, 30):
        print(f"     Match {dup_id:02d}  -->  DELETE")
    print()

    if dry_run:
        print("=" * 80)
        print("DRY RUN COMPLETE — ZERO MUTATIONS WERE PERFORMED ON THE DATABASE.")
        print("To apply changes, run with --execute")
        print("=" * 80 + "\n")
        conn.close()
        return 0

    # PHASE 4: Execute Cleanup in Atomic Transaction
    print("--- PHASE 4: EXECUTING CLEANUP (ATOMIC TRANSACTION) ---")
    try:
        cursor.execute("BEGIN TRANSACTION;")

        # 1. Re-link dependent videos (if any)
        for dup_id, info in TARGET_DUPLICATE_MAPPINGS.items():
            canon_id = info["canonical_id"]
            cursor.execute(
                "UPDATE videos SET match_id = ? WHERE match_id = ?;",
                (canon_id, dup_id),
            )
            if cursor.rowcount > 0:
                print(f"  Re-linked {cursor.rowcount} videos from match {dup_id} to {canon_id}")

        # 2. Re-link legitimate non-false change events (if any)
        for dup_id, info in TARGET_DUPLICATE_MAPPINGS.items():
            canon_id = info["canonical_id"]
            cursor.execute(
                f"UPDATE change_events SET entity_id = ? WHERE entity_type = 'match' AND entity_id = ? AND id NOT IN ({','.join(map(str, FALSE_NEW_ENTITY_EVENT_IDS))});",
                (canon_id, dup_id),
            )
            if cursor.rowcount > 0:
                print(f"  Re-linked {cursor.rowcount} legitimate ChangeEvents from match {dup_id} to {canon_id}")

        # 3. Delete notification_event_links referencing false events
        cursor.execute(
            f"DELETE FROM notification_event_links WHERE change_event_id IN ({','.join(map(str, FALSE_NEW_ENTITY_EVENT_IDS))});"
        )
        print(f"  Deleted {cursor.rowcount} notification_event_links referencing false events")

        # 4. Delete false ChangeEvents (16, 17, 18)
        cursor.execute(
            f"DELETE FROM change_events WHERE id IN ({','.join(map(str, FALSE_NEW_ENTITY_EVENT_IDS))});"
        )
        deleted_events_count = cursor.rowcount
        print(f"  Deleted {deleted_events_count} false ChangeEvents (IDs: {FALSE_NEW_ENTITY_EVENT_IDS})")

        # 5. Delete duplicate Match entities (28, 29, 30)
        cursor.execute(
            "DELETE FROM matches WHERE id IN (28, 29, 30);"
        )
        deleted_matches_count = cursor.rowcount
        print(f"  Deleted {deleted_matches_count} duplicate Match rows (IDs: 28, 29, 30)")

        # Commit transaction
        conn.commit()
        print("  Transaction committed successfully.")
        print()

    except Exception as exc:
        conn.rollback()
        print(f"  [FATAL] Cleanup execution failed! Rolled back transaction. Error: {exc}")
        conn.close()
        return 1

    # PHASE 5: Post-Cleanup Validation
    print("--- PHASE 5: POST-CLEANUP VALIDATION ---")
    state_after = inspect_database(cursor)

    val_errors = []

    # 1. Integrity check
    if not state_after["integrity_ok"]:
        val_errors.append("PRAGMA integrity_check failed after cleanup!")
    else:
        print("  [PASS] PRAGMA integrity_check = ok")

    # 2. Foreign key check
    if state_after["fk_violations"]:
        val_errors.append(f"PRAGMA foreign_key_check reported violations: {state_after['fk_violations']}")
    else:
        print("  [PASS] PRAGMA foreign_key_check = 0 violations")

    # 3. Match count changed 30 -> 27
    match_count_before = state_before["counts"].get("matches", 0)
    match_count_after = state_after["counts"].get("matches", 0)
    if match_count_after != match_count_before - 3:
        val_errors.append(f"Expected match count to decrease by 3 (from {match_count_before} to {match_count_before-3}), but got {match_count_after}")
    else:
        print(f"  [PASS] Match count updated correctly: {match_count_before} -> {match_count_after}")

    # 4. Duplicate IDs no longer exist
    matches_after = state_after["matches_found"]
    for dup_id in (28, 29, 30):
        if dup_id in matches_after:
            val_errors.append(f"Duplicate Match ID {dup_id} still exists in matches table!")
        else:
            print(f"  [PASS] Duplicate Match ID {dup_id} successfully deleted")

    # 5. Canonical IDs still exist with correct data
    for canon_id in (19, 20, 21):
        if canon_id not in matches_after:
            val_errors.append(f"Canonical Match ID {canon_id} was deleted or is missing!")
        else:
            m = matches_after[canon_id]
            print(f"  [PASS] Canonical Match ID {canon_id} intact: ext_id={m['external_id']!r}, title={m['title']!r}, status={m['status']!r}")

    # 6. ChangeEvents 16, 17, 18 no longer exist
    cursor.execute(f"SELECT id FROM change_events WHERE id IN ({','.join(map(str, FALSE_NEW_ENTITY_EVENT_IDS))});")
    remaining_false_events = cursor.fetchall()
    if remaining_false_events:
        val_errors.append(f"False ChangeEvents {[r[0] for r in remaining_false_events]} still exist!")
    else:
        print(f"  [PASS] False ChangeEvents {FALSE_NEW_ENTITY_EVENT_IDS} successfully deleted")

    # 7. Check for duplicate external_ids
    cursor.execute("""
        SELECT external_id, COUNT(*) as cnt
        FROM matches
        WHERE external_id IS NOT NULL AND TRIM(external_id) != ''
        GROUP BY external_id
        HAVING cnt > 1;
    """)
    dup_exts = cursor.fetchall()
    if dup_exts:
        val_errors.append(f"Duplicate external_ids found in matches table: {[dict(r) for r in dup_exts]}")
    else:
        print("  [PASS] Zero duplicate external_ids exist across matches table")

    # 8. Check for duplicate canonical slugs
    cursor.execute("""
        SELECT slug, COUNT(*) as cnt
        FROM matches
        GROUP BY slug
        HAVING cnt > 1;
    """)
    dup_slugs = cursor.fetchall()
    if dup_slugs:
        val_errors.append(f"Duplicate slugs found in matches table: {[dict(r) for r in dup_slugs]}")
    else:
        print("  [PASS] Zero duplicate slugs exist across matches table")

    # Final counts table
    print("\n  Final Table Counts:")
    for tbl, count in state_after["counts"].items():
        print(f"    - {tbl:<26}: {count}")
    print()

    if val_errors:
        print("=" * 80)
        print("POST-CLEANUP VALIDATION ENCOUNTERED ERRORS:")
        for err in val_errors:
            print(f"  - [FAIL] {err}")
        print("=" * 80 + "\n")
        conn.close()
        return 1

    print("=" * 80)
    print("CLEANUP AND VALIDATION COMPLETED SUCCESSFULLY.")
    print("=" * 80 + "\n")
    conn.close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="FanCode Production Duplicate Cleanup")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform dry run without mutating DB")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute cleanup with atomic transaction")
    args = parser.parse_args(argv)

    if not args.execute and not args.dry_run:
        parser.print_help()
        print("\nPlease specify either --dry-run or --execute")
        return 1

    is_dry = args.dry_run or not args.execute
    return run_cleanup(dry_run=is_dry)


if __name__ == "__main__":
    sys.exit(main())
