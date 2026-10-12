"""
backfill_match_external_ids.py – Safe Production Database External-ID Backfill & Duplicate Resolution Script.

Performs:
1. Pre-inspection and audit of all Match rows where external_id IS NULL or requires canonical deduplication.
2. Extraction of FanCode match IDs from canonical source_urls using extract_match_id_from_url.
3. Safe canonical grouping and duplicate resolution (Rules 1-4: Deep Tour URL, Semantic Slug, Metadata Richness, Tie-breaker).
4. Non-destructive field enrichment from duplicate rows into canonical rows.
5. Re-linking of dependent foreign-key records (videos.match_id) and change events (change_events.entity_id).
6. Byte-for-byte timestamped database backup with SHA-256 verification (before execution).
7. Dry run mode (--dry-run) with zero mutations and comprehensive audit/plan reporting.
8. Atomic transaction execution (--execute) with rollback on any failure.
9. Post-backfill validation (integrity_check, foreign_key_check, row counts, zero NULLs, distinct external_ids).
10. Strict invariant preservation (existing non-null external_ids are never overwritten).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.discovery.url_normalizer import extract_match_id_from_url

DB_PATH = ROOT / "data" / "fancode.db"
BACKUP_DIR = ROOT / "data" / "backups"

GENERIC_URLS = {
    "https://www.fancode.com",
    "https://www.fancode.com/",
    "https://www.fancode.com/live",
    "https://www.fancode.com/live-now",
    "https://www.fancode.com/live-now/all-sports",
    "https://www.fancode.com/schedule",
    "https://www.fancode.com/sports",
    "https://www.fancode.com/video",
}

ENRICHABLE_FIELDS = [
    "tour_id",
    "sport_id",
    "match_date",
    "start_time",
    "status",
    "venue",
    "team_a_name",
    "team_a_external_id",
    "team_b_name",
    "team_b_external_id",
    "team_a_logo_url",
    "team_b_logo_url",
    "score_summary",
    "image_url",
]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def create_backup(db_path: Path) -> Tuple[Path, str, str, int]:
    """Create a byte-for-byte timestamped backup and verify SHA-256 and integrity."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"fancode_before_external_id_backfill_{timestamp}.db"

    # Compute original hash & size
    orig_hash = compute_sha256(db_path)
    orig_size = db_path.stat().st_size

    # Perform file copy
    shutil.copy2(db_path, backup_path)

    # Verify backup hash & size
    backup_hash = compute_sha256(backup_path)
    backup_size = backup_path.stat().st_size

    if orig_hash != backup_hash or orig_size != backup_size:
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(f"Backup verification failed: hash/size mismatch ({orig_hash} != {backup_hash})")

    # Verify backup SQLite integrity
    b_conn = sqlite3.connect(backup_path.as_posix())
    b_cur = b_conn.cursor()
    b_cur.execute("PRAGMA integrity_check;")
    b_res = b_cur.fetchall()
    b_conn.close()
    if not (len(b_res) == 1 and b_res[0][0] == "ok"):
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(f"Backup SQLite integrity_check failed: {b_res}")

    return backup_path, orig_hash, backup_hash, orig_size


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


def _is_deep_tour_url(url: Optional[str]) -> bool:
    """Return True if URL is a full tour-scoped match URL."""
    if not url:
        return False
    u = url.lower()
    return "/tour/" in u and "/matches/" in u


def _is_generic_slug(slug: Optional[str]) -> bool:
    """Return True if slug is generic or ordinal (e.g. match-10)."""
    if not slug:
        return True
    s = slug.lower().strip()
    return s.startswith("match-") or s in ("match", "live", "schedule", "cricket")


def select_canonical_match(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Select the canonical Match record from a list of records sharing the same extracted external_id.

    Ranking Criteria:
    1. Deep Tour URL: Prefer source_url containing '/tour/.../matches/...' over short '/matches/...' URLs.
    2. Semantic Slug: Prefer semantic slug (e.g. 'thailand-vs-bhutan') over generic slug (e.g. 'match-10').
    3. Metadata Richness: Prefer row with more populated non-null fields (venue, status, score_summary, tour_id, etc.).
    4. Deterministic Tie-breaker: Prefer lower primary key (id).

    Returns:
        (canonical_row, list_of_duplicate_rows)
    """
    if not rows:
        raise ValueError("Cannot select canonical match from empty row list")
    if len(rows) == 1:
        return rows[0], []

    def rank_key(row: Dict[str, Any]):
        url = row.get("source_url") or ""
        slug = row.get("slug") or ""
        row_id = row.get("id") or 0

        # Score 1: Deep tour URL (1 if deep tour, 0 otherwise)
        deep_score = 1 if _is_deep_tour_url(url) else 0

        # Score 2: Semantic slug (1 if semantic, 0 if generic)
        slug_score = 0 if _is_generic_slug(slug) else 1

        # Score 3: Richness of fields
        richness = sum(
            1 for k in [
                "venue", "status", "score_summary", "tour_id", "sport_id",
                "team_a_name", "team_b_name", "start_time", "match_date"
            ]
            if row.get(k) is not None and str(row.get(k)).strip() != ""
        )

        # Higher scores rank first (negative), lower row_id ranks first (positive)
        return (-deep_score, -slug_score, -richness, row_id)

    sorted_rows = sorted(rows, key=rank_key)
    canonical = sorted_rows[0]
    duplicates = sorted_rows[1:]
    return canonical, duplicates


def compute_merged_attributes(canonical: Dict[str, Any], duplicates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute non-destructive field enrichments from duplicate rows into the canonical row.
    Only fields that are NULL or empty in the canonical row are populated from duplicates.
    """
    updates: Dict[str, Any] = {}
    for field in ENRICHABLE_FIELDS:
        canon_val = canonical.get(field)
        if canon_val is None or str(canon_val).strip() == "":
            for dup in duplicates:
                dup_val = dup.get(field)
                if dup_val is not None and str(dup_val).strip() != "":
                    updates[field] = dup_val
                    break
    return updates


def run_audit(cursor: sqlite3.Cursor) -> Dict[str, Any]:
    """Inspect current database state, group candidates by extracted ID, and plan safe duplicate resolution."""
    # Integrity check
    cursor.execute("PRAGMA integrity_check;")
    integrity_res = cursor.fetchall()
    integrity_ok = len(integrity_res) == 1 and integrity_res[0][0] == "ok"

    # Foreign key check
    cursor.execute("PRAGMA foreign_key_check;")
    fk_violations = cursor.fetchall()

    # Table counts
    counts = get_table_counts(cursor)

    # Fetch all matches
    cursor.execute(
        "SELECT id, external_id, title, slug, source_url, status, start_time, match_date, "
        "team_a_name, team_a_external_id, team_b_name, team_b_external_id, team_a_logo_url, team_b_logo_url, "
        "venue, score_summary, image_url, tour_id, sport_id, created_at, updated_at, last_seen_at "
        "FROM matches ORDER BY id ASC;"
    )
    all_matches = [dict(row) for row in cursor.fetchall()]

    errors = []
    grouped_by_ext_id: Dict[str, List[Dict[str, Any]]] = {}
    unextractable_matches: List[Dict[str, Any]] = []

    for m in all_matches:
        db_id = m["id"]
        source_url = m["source_url"] or ""

        # Query dependent records count for this match
        cursor.execute("SELECT COUNT(*) FROM videos WHERE match_id = ?;", (db_id,))
        m["dependent_videos_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM change_events WHERE entity_type = 'match' AND entity_id = ?;", (db_id,))
        m["dependent_change_events_count"] = cursor.fetchone()[0]

        # Check if generic URL
        clean_url = source_url.strip().rstrip("/")
        if clean_url in GENERIC_URLS or clean_url.endswith(("/schedule", "/live-now", "/sports", "/video", "/live")):
            errors.append(f"Match ID {db_id} has generic source_url: {source_url!r}")

        extracted_id = extract_match_id_from_url(source_url)
        if not extracted_id or not extracted_id.isdigit():
            # If match already has a valid external_id, use that
            if m["external_id"] and str(m["external_id"]).isdigit():
                extracted_id = str(m["external_id"])
            else:
                errors.append(f"Match ID {db_id}: Failed to extract valid numeric match ID from source_url {source_url!r}")
                unextractable_matches.append(m)

        if extracted_id:
            m["extracted_external_id"] = extracted_id
            grouped_by_ext_id.setdefault(extracted_id, []).append(m)

    # Build resolution plan
    resolution_plan: List[Dict[str, Any]] = []
    duplicate_groups: List[Dict[str, Any]] = []
    single_candidates: List[Dict[str, Any]] = []
    total_duplicate_rows_to_remove = 0

    for ext_id, rows in grouped_by_ext_id.items():
        canonical, duplicates = select_canonical_match(rows)
        enrichments = compute_merged_attributes(canonical, duplicates) if duplicates else {}
        dup_ids = [d["id"] for d in duplicates]
        total_duplicate_rows_to_remove += len(duplicates)

        plan_item = {
            "external_id": ext_id,
            "canonical": canonical,
            "duplicates": duplicates,
            "duplicate_ids": dup_ids,
            "enrichments": enrichments,
            "is_duplicate_group": len(duplicates) > 0,
        }
        resolution_plan.append(plan_item)

        if duplicates:
            duplicate_groups.append(plan_item)
        else:
            single_candidates.append(plan_item)

    expected_final_matches = len(all_matches) - total_duplicate_rows_to_remove
    distinct_external_ids_count = len(grouped_by_ext_id)

    return {
        "integrity_ok": integrity_ok,
        "fk_violations": fk_violations,
        "counts": counts,
        "all_matches": all_matches,
        "resolution_plan": resolution_plan,
        "duplicate_groups": duplicate_groups,
        "single_candidates": single_candidates,
        "total_duplicate_rows_to_remove": total_duplicate_rows_to_remove,
        "expected_final_matches": expected_final_matches,
        "distinct_external_ids_count": distinct_external_ids_count,
        "errors": errors,
    }


def execute_backfill_transaction(
    conn: sqlite3.Connection,
    audit: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes backfill and safe canonical duplicate resolution in an atomic transaction.
    Raises an exception on any assertion failure to trigger complete rollback.
    """
    cursor = conn.cursor()
    total_matches_before = audit["counts"].get("matches", 0)
    total_events_before = audit["counts"].get("change_events", 0)
    total_runs_before = audit["counts"].get("scrape_runs", 0)
    total_batches_before = audit["counts"].get("notification_batches", 0)
    total_deliveries_before = audit["counts"].get("notification_deliveries", 0)
    total_links_before = audit["counts"].get("notification_event_links", 0)

    expected_final_matches = audit["expected_final_matches"]

    canonical_updates = 0
    duplicates_deleted = 0
    videos_relinked = 0
    change_events_relinked = 0

    cursor.execute("BEGIN TRANSACTION;")

    for item in audit["resolution_plan"]:
        ext_id = item["external_id"]
        canonical = item["canonical"]
        duplicates = item["duplicates"]
        enrichments = item["enrichments"]

        canon_id = canonical["id"]

        # Invariant check: if canonical already has a non-null external_id, verify it matches
        curr_canon_ext = canonical.get("external_id")
        if curr_canon_ext is not None and str(curr_canon_ext).strip() != "":
            if str(curr_canon_ext) != str(ext_id):
                raise RuntimeError(
                    f"Invariant violation on Match ID {canon_id}: existing external_id '{curr_canon_ext}' != target '{ext_id}'"
                )

        # 1. Re-link foreign keys and polymorphic references from duplicates
        for dup in duplicates:
            dup_id = dup["id"]

            # Re-link videos
            cursor.execute("UPDATE videos SET match_id = ? WHERE match_id = ?;", (canon_id, dup_id))
            videos_relinked += cursor.rowcount

            # Re-link change events from duplicate
            cursor.execute(
                "UPDATE change_events SET entity_id = ?, external_id = ? WHERE entity_type = 'match' AND entity_id = ?;",
                (canon_id, ext_id, dup_id),
            )
            change_events_relinked += cursor.rowcount

            # Delete the duplicate match row
            cursor.execute("DELETE FROM matches WHERE id = ?;", (dup_id,))
            duplicates_deleted += cursor.rowcount

        # 2. Update change events for the canonical match to ensure external_id is set
        cursor.execute(
            "UPDATE change_events SET external_id = ? WHERE entity_type = 'match' AND entity_id = ? AND (external_id IS NULL OR external_id = '');",
            (ext_id, canon_id),
        )

        # 3. Update canonical match record with external_id and any enriched fields
        set_clauses = ["external_id = ?"]
        set_params: List[Any] = [ext_id]

        for field_name, field_val in enrichments.items():
            set_clauses.append(f"{field_name} = ?")
            set_params.append(field_val)

        set_params.append(canon_id)
        sql = f"UPDATE matches SET {', '.join(set_clauses)} WHERE id = ?;"
        cursor.execute(sql, set_params)
        canonical_updates += cursor.rowcount

    # -------------------------------------------------------------------------
    # In-Transaction Assertions
    # -------------------------------------------------------------------------
    if canonical_updates != len(audit["resolution_plan"]):
        raise RuntimeError(f"Expected {len(audit['resolution_plan'])} canonical updates, got {canonical_updates}")

    if duplicates_deleted != audit["total_duplicate_rows_to_remove"]:
        raise RuntimeError(f"Expected {audit['total_duplicate_rows_to_remove']} deleted duplicates, got {duplicates_deleted}")

    cursor.execute("SELECT COUNT(*) FROM matches;")
    post_matches = cursor.fetchone()[0]
    if post_matches != expected_final_matches:
        raise RuntimeError(f"Expected {expected_final_matches} matches after merge, got {post_matches}")

    cursor.execute("SELECT COUNT(*) FROM matches WHERE external_id IS NULL;")
    post_nulls = cursor.fetchone()[0]
    if post_nulls != 0:
        raise RuntimeError(f"Found {post_nulls} NULL external_id rows remaining in transaction")

    cursor.execute("SELECT COUNT(DISTINCT external_id) FROM matches;")
    post_distinct = cursor.fetchone()[0]
    if post_distinct != expected_final_matches:
        raise RuntimeError(f"Expected {expected_final_matches} distinct external_ids, got {post_distinct}")

    cursor.execute("""
        SELECT external_id, COUNT(*) as cnt
        FROM matches
        GROUP BY external_id
        HAVING cnt > 1;
    """)
    post_dups = cursor.fetchall()
    if post_dups:
        raise RuntimeError(f"Found duplicate external_ids after merge: {[dict(d) for d in post_dups]}")

    cursor.execute("SELECT COUNT(*) FROM change_events;")
    post_events = cursor.fetchone()[0]
    if post_events != total_events_before:
        raise RuntimeError(f"change_events count changed: {total_events_before} -> {post_events}")

    cursor.execute("SELECT COUNT(*) FROM scrape_runs;")
    post_runs = cursor.fetchone()[0]
    if post_runs != total_runs_before:
        raise RuntimeError(f"scrape_runs count changed: {total_runs_before} -> {post_runs}")

    cursor.execute("SELECT COUNT(*) FROM notification_batches;")
    post_batches = cursor.fetchone()[0]
    if post_batches != total_batches_before:
        raise RuntimeError(f"notification_batches count changed: {total_batches_before} -> {post_batches}")

    cursor.execute("SELECT COUNT(*) FROM notification_deliveries;")
    post_deliveries = cursor.fetchone()[0]
    if post_deliveries != total_deliveries_before:
        raise RuntimeError(f"notification_deliveries count changed: {total_deliveries_before} -> {post_deliveries}")

    cursor.execute("SELECT COUNT(*) FROM notification_event_links;")
    post_links = cursor.fetchone()[0]
    if post_links != total_links_before:
        raise RuntimeError(f"notification_event_links count changed: {total_links_before} -> {post_links}")

    cursor.execute("PRAGMA foreign_key_check;")
    fk_res = cursor.fetchall()
    if fk_res:
        raise RuntimeError(f"PRAGMA foreign_key_check failed: {fk_res}")

    cursor.execute("PRAGMA integrity_check;")
    integ_res = cursor.fetchall()
    if not (len(integ_res) == 1 and integ_res[0][0] == "ok"):
        raise RuntimeError(f"PRAGMA integrity_check failed: {integ_res}")

    conn.commit()

    return {
        "canonical_updates": canonical_updates,
        "duplicates_deleted": duplicates_deleted,
        "videos_relinked": videos_relinked,
        "change_events_relinked": change_events_relinked,
        "post_matches": post_matches,
        "post_nulls": post_nulls,
        "post_distinct": post_distinct,
    }


def run_backfill(dry_run: bool = True) -> int:
    print("\n" + "=" * 90)
    print(f"   FANCODE MONITOR — PRODUCTION EXTERNAL-ID BACKFILL ({'DRY RUN' if dry_run else 'EXECUTE'})")
    print("=" * 90)
    print(f"Database Path : {DB_PATH}")
    print(f"Mode          : {'DRY RUN (No mutations will be made)' if dry_run else 'EXECUTE (Atomic transaction)'}")
    print("=" * 90 + "\n")

    if not DB_PATH.exists():
        print(f"[FATAL] Database not found at {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # PHASE 1: Pre-backfill Audit
    print("--- STEP 1: PRE-BACKFILL AUDIT & RESOLUTION PLANNING ---")
    audit = run_audit(cursor)

    print(f"  PRAGMA integrity_check : {'PASS (ok)' if audit['integrity_ok'] else 'FAIL'}")
    print(f"  Foreign Key Violations : {len(audit['fk_violations'])}")
    if audit["fk_violations"]:
        print(f"  [ERROR] Foreign key violations present: {audit['fk_violations']}")
        conn.close()
        return 1

    total_matches = audit["counts"].get("matches", 0)
    total_events = audit["counts"].get("change_events", 0)
    total_runs = audit["counts"].get("scrape_runs", 0)
    print(f"  Total Matches in DB    : {total_matches}")
    print(f"  Total ChangeEvents     : {total_events}")
    print(f"  Total ScrapeRuns       : {total_runs}")
    print(f"  Distinct Extracted IDs : {audit['distinct_external_ids_count']}")
    print(f"  Duplicate Groups Found : {len(audit['duplicate_groups'])}")
    print(f"  Duplicates to Remove   : {audit['total_duplicate_rows_to_remove']}")
    print(f"  Expected Final Matches : {audit['expected_final_matches']}")
    print()

    # Check for any audit errors
    if audit["errors"]:
        print("  [FATAL] Audit validation encountered errors:")
        for err in audit["errors"]:
            print(f"    - {err}")
        print("\nStopping before any modification.\n")
        conn.close()
        return 1

    # Display duplicate groups resolution plan
    if audit["duplicate_groups"]:
        print("  Duplicate Resolution Groups:")
        print("  " + "-" * 86)
        for g in audit["duplicate_groups"]:
            c = g["canonical"]
            print(f"  [DUPLICATE GROUP] External ID: {g['external_id']}")
            print(f"    - Canonical Match ID {c['id']:<3} : {c['title']} (Slug: {c['slug']})")
            print(f"      Source URL       : {c['source_url']}")
            print(f"      Dependent Records: videos={c.get('dependent_videos_count', 0)}, change_events={c.get('dependent_change_events_count', 0)}")
            for d in g["duplicates"]:
                print(f"    - Duplicate Match ID {d['id']:<3} : {d['title']} (Slug: {d['slug']})")
                print(f"      Source URL       : {d['source_url']}")
                print(f"      Dependent Records: videos={d.get('dependent_videos_count', 0)}, change_events={d.get('dependent_change_events_count', 0)}")
                print(f"      Action           : Re-link dependents to Match {c['id']}, delete duplicate row Match {d['id']}")
            if g["enrichments"]:
                print(f"      Proposed Enrichment: {g['enrichments']}")
            print(f"      Proposed Changes : Update Match {c['id']} (set external_id='{g['external_id']}')")
            print(f"      Proposed Deletes : Delete Match {[d['id'] for d in g['duplicates']]}")
            print()
        print("  " + "-" * 86 + "\n")

    # Display full resolution mapping plan
    print("  Candidate Backfill Resolution Plan:")
    print("  " + "-" * 86)
    print(f"  {'Action':<10} | {'DB ID':<6} | {'Extracted Ext ID':<17} | {'Title':<30} | {'Slug'}")
    print("  " + "-" * 86)
    for item in audit["resolution_plan"]:
        c = item["canonical"]
        print(f"  {'KEEP/UPDATE':<10} | {c['id']:<6} | {item['external_id']:<17} | {c['title'][:30]:<30} | {c['slug']}")
        for d in item["duplicates"]:
            print(f"  {'MERGE/DEL':<10} | {d['id']:<6} | {item['external_id']:<17} | {d['title'][:30]:<30} | {d['slug']}")
    print("  " + "-" * 86 + "\n")

    # PHASE 2: Database Backup
    backup_path = None
    orig_hash = None
    backup_hash = None
    db_size = 0

    if not dry_run:
        print("--- STEP 2: DATABASE BACKUP ---")
        try:
            backup_path, orig_hash, backup_hash, db_size = create_backup(DB_PATH)
            print(f"  Backup Created : {backup_path}")
            print(f"  Database Size  : {db_size:,} bytes")
            print(f"  Original SHA256: {orig_hash}")
            print(f"  Backup SHA256  : {backup_hash}")
            print(f"  Verification   : MATCH (byte-for-byte exact, SQLite integrity verified)")
            print()
        except Exception as exc:
            print(f"  [FATAL] Backup creation failed: {exc}")
            conn.close()
            return 1
    else:
        print("--- STEP 2: DATABASE BACKUP (SKIPPED IN DRY-RUN) ---")
        orig_hash = compute_sha256(DB_PATH)
        db_size = DB_PATH.stat().st_size
        print(f"  Database Size  : {db_size:,} bytes")
        print(f"  Original SHA256: {orig_hash}")
        print()

    if dry_run:
        print("=" * 90)
        print("DRY RUN COMPLETE — ZERO MUTATIONS WERE PERFORMED ON THE DATABASE.")
        print(f"Resolution plan: {audit['expected_final_matches']} canonical matches, {audit['total_duplicate_rows_to_remove']} duplicate rows to merge.")
        print("All candidate groups were successfully validated with distinct extracted external_ids.")
        print("To execute backfill migration, run with --execute")
        print("=" * 90 + "\n")
        conn.close()
        return 0

    # PHASE 3: Execute Backfill inside Atomic Transaction
    print("--- STEP 3: EXECUTING BACKFILL IN ATOMIC TRANSACTION ---")
    try:
        res = execute_backfill_transaction(conn, audit)
        print(f"  Canonical rows updated  : {res['canonical_updates']}")
        print(f"  Duplicate rows deleted  : {res['duplicates_deleted']}")
        print(f"  Videos re-linked        : {res['videos_relinked']}")
        print(f"  Change events re-linked : {res['change_events_relinked']}")
        print("  [SUCCESS] In-transaction assertions passed. Transaction committed.")
        print()
    except Exception as exc:
        conn.rollback()
        print(f"  [FATAL] Migration failed! Transaction rolled back. Error: {exc}")
        conn.close()
        return 1

    # PHASE 4: Post-Backfill Comprehensive Validation
    print("--- STEP 4: POST-BACKFILL VALIDATION ---")
    post_audit = run_audit(cursor)

    val_errors = []

    # 1. Integrity check
    if not post_audit["integrity_ok"]:
        val_errors.append("PRAGMA integrity_check failed after backfill!")
    else:
        print("  [PASS] PRAGMA integrity_check = ok")

    # 2. Foreign key check
    if post_audit["fk_violations"]:
        val_errors.append(f"PRAGMA foreign_key_check reported violations: {post_audit['fk_violations']}")
    else:
        print("  [PASS] PRAGMA foreign_key_check = 0 violations")

    # 3. Match count
    post_matches = post_audit["counts"].get("matches", 0)
    expected_matches = audit["expected_final_matches"]
    if post_matches != expected_matches:
        val_errors.append(f"Match count mismatch: expected={expected_matches}, after={post_matches}")
    else:
        print(f"  [PASS] Match count as expected: {expected_matches}")

    # 4. Null external_id count
    cursor.execute("SELECT COUNT(*) FROM matches WHERE external_id IS NULL;")
    null_count = cursor.fetchone()[0]
    if null_count != 0:
        val_errors.append(f"Expected 0 NULL external_id rows, got {null_count}")
    else:
        print(f"  [PASS] NULL external_id count = {null_count}")

    # 5. Distinct external_ids
    cursor.execute("SELECT COUNT(DISTINCT external_id) FROM matches;")
    distinct_count = cursor.fetchone()[0]
    if distinct_count != expected_matches:
        val_errors.append(f"Expected {expected_matches} distinct external_ids, got {distinct_count}")
    else:
        print(f"  [PASS] Distinct external_ids count = {distinct_count}")

    # 6. Duplicate external_ids check
    cursor.execute("""
        SELECT external_id, COUNT(*) as cnt
        FROM matches
        GROUP BY external_id
        HAVING cnt > 1;
    """)
    dup_rows = cursor.fetchall()
    if dup_rows:
        val_errors.append(f"Duplicate external_ids found: {[dict(r) for r in dup_rows]}")
    else:
        print("  [PASS] Duplicate external_ids = 0")

    # 7. Change events count
    post_events = post_audit["counts"].get("change_events", 0)
    if post_events != total_events:
        val_errors.append(f"Change events count mismatch: before={total_events}, after={post_events}")
    else:
        print(f"  [PASS] Change events count unchanged: {total_events} -> {post_events}")

    # 8. Scrape runs count
    post_runs = post_audit["counts"].get("scrape_runs", 0)
    if post_runs != total_runs:
        val_errors.append(f"Scrape runs count mismatch: before={total_runs}, after={post_runs}")
    else:
        print(f"  [PASS] Scrape runs count unchanged: {total_runs} -> {post_runs}")

    # 9. Verify canonical mappings
    for item in audit["resolution_plan"]:
        c_id = item["canonical"]["id"]
        expected_ext = item["external_id"]
        cursor.execute("SELECT id, external_id FROM matches WHERE id = ?;", (c_id,))
        row = cursor.fetchone()
        if not row:
            val_errors.append(f"Canonical Match ID {c_id} missing from database!")
        elif row["external_id"] != expected_ext:
            val_errors.append(f"Match ID {c_id} expected external_id={expected_ext}, got {row['external_id']}")
        else:
            print(f"  [PASS] Canonical Match ID {c_id:02d} -> external_id {expected_ext}")

    # 10. Verify duplicate IDs are deleted
    for g in audit["duplicate_groups"]:
        for d in g["duplicates"]:
            d_id = d["id"]
            cursor.execute("SELECT id FROM matches WHERE id = ?;", (d_id,))
            if cursor.fetchone() is not None:
                val_errors.append(f"Duplicate Match ID {d_id} was NOT deleted!")
            else:
                print(f"  [PASS] Duplicate Match ID {d_id:02d} deleted successfully")

    print()
    if val_errors:
        print("=" * 90)
        print("POST-BACKFILL VALIDATION ENCOUNTERED ERRORS:")
        for err in val_errors:
            print(f"  - [FAIL] {err}")
        print("=" * 90 + "\n")
        conn.close()
        return 1

    print("=" * 90)
    print("BACKFILL AND VALIDATION COMPLETED SUCCESSFULLY WITH ZERO ERRORS.")
    print("=" * 90 + "\n")
    conn.close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="FanCode Match External-ID Backfill")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform dry run without mutating DB")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute backfill with atomic transaction")
    args = parser.parse_args(argv)

    if not args.execute and not args.dry_run:
        # Default to dry-run
        args.dry_run = True

    is_dry = args.dry_run and not args.execute
    return run_backfill(dry_run=is_dry)


if __name__ == "__main__":
    sys.exit(main())
