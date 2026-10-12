"""
audit_production_db.py – READ-ONLY Production Database Audit & Duplicate Entity Inspector.

Safely inspects data/fancode.db to:
1. Run SQLite integrity and foreign key checks.
2. Scan for duplicate Match entities (by external_id, source_url, slug, base-slug, title).
3. Inspect related ChangeEvents for suspected duplicates and specifically Run 188.
4. Evaluate canonical vs duplicate status using strict priority rules.
5. Generate a proposed safe cleanup migration table and SQL/ORM statements WITHOUT executing them.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fancode.db"


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    clean = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(clean.split())


def get_base_slug(slug: Optional[str]) -> str:
    if not slug:
        return ""
    return re.sub(r"-\d+$", "", slug.lower().strip())


def run_audit() -> int:
    if not DB_PATH.exists():
        print(f"[ERROR] Database file not found at: {DB_PATH}")
        return 1

    # Open read-only SQLite connection (URI mode)
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("      FANCODE MONITOR — READ-ONLY PRODUCTION DATABASE AUDIT")
    print("=" * 80)
    print(f"Database File: {DB_PATH}")
    print(f"Mode         : READ-ONLY (No modifications will be made)")
    print("=" * 80 + "\n")

    # 1. SQLite Integrity & Foreign Key Checks
    print("--- 1. DATABASE INTEGRITY & METRICS ---")
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchall()
    integrity_status = integrity[0][0] if integrity else "UNKNOWN"
    print(f"  PRAGMA integrity_check : {integrity_status}")

    cursor.execute("PRAGMA foreign_key_check;")
    fk_violations = cursor.fetchall()
    print(f"  Foreign Key Violations : {len(fk_violations)}")
    if fk_violations:
        for v in fk_violations:
            print(f"    - Violation: {dict(v)}")

    # Entity counts
    tables = ["sports", "tours", "matches", "videos", "pages", "change_events", "scrape_runs", "notification_batches", "notification_deliveries"]
    counts = {}
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t};")
            counts[t] = cursor.fetchone()[0]
        except Exception:
            counts[t] = "N/A"

    print("  Entity Row Counts:")
    for t, c in counts.items():
        print(f"    - {t:<24}: {c}")
    print()

    # 2. Fetch all Matches
    cursor.execute("""
        SELECT id, external_id, title, slug, source_url, status, venue,
               start_time, match_date, team_a_name, team_b_name, score_summary,
               sport_id, tour_id, created_at, updated_at, last_seen_at
        FROM matches
        ORDER BY id ASC;
    """)
    all_matches = [dict(r) for r in cursor.fetchall()]
    print(f"--- 2. ALL MATCH ENTITIES ({len(all_matches)} total) ---")
    for m in all_matches:
        print(f"  [ID {m['id']:02d}] ext_id={m['external_id']!r:<10} status={m['status']!r:<10} slug={m['slug']!r:<35} title={m['title']!r}")
        print(f"        URL: {m['source_url']}")
        print(f"        Created: {m['created_at']} | Updated: {m['updated_at']} | Last seen: {m['last_seen_at']}")
    print()

    # 3. Duplicate Detection & Grouping
    print("--- 3. DUPLICATE ANALYSIS & GROUPING ---")

    # Import URL ID extractor
    sys.path.insert(0, str(ROOT))
    from app.scraper.live_now.normalizer import extract_match_id_from_url
    from app.scraper.discovery.url_normalizer import normalize as normalize_url

    GENERIC_SLUGS = {"match", "matches", "unnamed-match", "fixture", "fixtures", "game", "games", "event", "events"}
    GENERIC_URLS = {
        "https://www.fancode.com",
        "https://www.fancode.com/",
        "https://www.fancode.com/live",
        "https://www.fancode.com/live-now",
        "https://www.fancode.com/live-now/all-sports",
        "https://www.fancode.com/schedule",
        "https://www.fancode.com/video",
    }

    # Signal 1: Group by explicit external_id
    ext_id_groups: Dict[str, List[dict]] = {}
    for m in all_matches:
        ext = m.get("external_id")
        if ext and str(ext).strip():
            ext_id_groups.setdefault(str(ext).strip(), []).append(m)

    dup_ext_ids = {k: v for k, v in ext_id_groups.items() if len(v) > 1}
    print(f"  Signal 1 - Explicit External ID Duplicate Groups: {len(dup_ext_ids)}")
    for ext, members in dup_ext_ids.items():
        ids = [m['id'] for m in members]
        print(f"    - External ID {ext!r}: Match IDs {ids}")

    # Signal 2: Group by extracted match ID from source_url
    url_id_groups: Dict[str, List[dict]] = {}
    for m in all_matches:
        raw_url = m.get("source_url")
        if raw_url:
            extracted_id = extract_match_id_from_url(raw_url)
            if extracted_id:
                url_id_groups.setdefault(extracted_id, []).append(m)

    dup_url_ids = {k: v for k, v in url_id_groups.items() if len(v) > 1}
    print(f"  Signal 2 - Extracted URL Match ID Duplicate Groups: {len(dup_url_ids)}")
    for extracted_id, members in dup_url_ids.items():
        ids = [m['id'] for m in members]
        print(f"    - URL Match ID {extracted_id!r}: Match IDs {ids}")

    # Signal 3: Group by specific canonical match URL (excluding generic listing URLs)
    url_groups: Dict[str, List[dict]] = {}
    for m in all_matches:
        raw_url = m.get("source_url")
        if raw_url:
            norm = normalize_url(raw_url) or raw_url
            if norm not in GENERIC_URLS:
                url_groups.setdefault(norm, []).append(m)

    dup_urls = {k: v for k, v in url_groups.items() if len(v) > 1}
    print(f"  Signal 3 - Specific Source URL Duplicate Groups: {len(dup_urls)}")
    for u, members in dup_urls.items():
        ids = [m['id'] for m in members]
        print(f"    - URL {u!r}: Match IDs {ids}")

    # Signal 4: Specific match slug (must have -vs- or -v- and not be generic)
    slug_groups: Dict[str, List[dict]] = {}
    for m in all_matches:
        slug = (m.get("slug") or "").strip().lower()
        base_slug = get_base_slug(slug)
        if base_slug and base_slug not in GENERIC_SLUGS and not re.match(r"^match(-\d+)?$", base_slug):
            if "-vs-" in base_slug or "-v-" in base_slug:
                slug_groups.setdefault(base_slug, []).append(m)

    dup_slugs = {k: v for k, v in slug_groups.items() if len(v) > 1}
    print(f"  Signal 4 - Specific Team vs Team Slug Duplicate Groups: {len(dup_slugs)}")
    for s, members in dup_slugs.items():
        ids = [m['id'] for m in members]
        print(f"    - Team Slug {s!r}: Match IDs {ids}")
    print()

    # 4. Suspected Duplicate Groups & Related ChangeEvents
    print("--- 4. SUSPECTED DUPLICATE GROUPS & CHANGE EVENTS ---")
    all_duplicate_match_ids = set()
    proposed_pairs: List[Dict[str, Any]] = []

    all_dup_groups: List[List[dict]] = []
    seen_ids_in_groups = set()

    for candidate_dict in (dup_ext_ids, dup_url_ids, dup_urls, dup_slugs):
        for group in candidate_dict.values():
            group_ids = tuple(sorted(m["id"] for m in group))
            if group_ids not in seen_ids_in_groups and len(group) > 1:
                seen_ids_in_groups.add(group_ids)
                all_dup_groups.append(group)

    for i, group in enumerate(all_dup_groups, 1):
        print(f"\n  [Group {i}]")
        for m in group:
            print(f"    - Match ID {m['id']}: ext_id={m['external_id']!r}, slug={m['slug']!r}, status={m['status']!r}, title={m['title']!r}")
            print(f"      URL: {m['source_url']}")
            print(f"      Created: {m['created_at']}, Updated: {m['updated_at']}")

            # Fetch associated ChangeEvents
            cursor.execute("""
                SELECT id, change_type, field_name, old_value, new_value, detected_at, notified_at
                FROM change_events
                WHERE entity_type = 'match' AND entity_id = ?
                ORDER BY id ASC;
            """, (m["id"],))
            events = [dict(e) for e in cursor.fetchall()]
            print(f"      ChangeEvents ({len(events)}):")
            for ev in events:
                print(f"        * Event {ev['id']}: type={ev['change_type']}, field={ev['field_name']}, old={ev['old_value']!r}, new={ev['new_value']!r}, detected_at={ev['detected_at']}")

        # Canonical Selection using strict rules:
        # Rule 1: Valid external_id
        # Rule 2: Most specific/canonical URL (not /schedule or generic)
        # Rule 3: Earliest legitimate creation when otherwise equal
        # Rule 4: Richest data
        sorted_members = sorted(
            group,
            key=lambda m: (
                1 if (m["external_id"] and str(m["external_id"]).strip()) else 0,
                0 if (m["source_url"] and (m["source_url"].endswith("/schedule") or m["source_url"].endswith("/live-now/all-sports"))) else 1,
                1 if (m["venue"] or m["score_summary"] or (m["team_a_name"] and m["team_b_name"])) else 0,
                -m["id"],  # Earlier ID preferred when everything else equal
            ),
            reverse=True,
        )
        canonical = sorted_members[0]
        duplicates = sorted_members[1:]

        for dup in duplicates:
            all_duplicate_match_ids.add(dup["id"])
            proposed_pairs.append({
                "canonical_id": canonical["id"],
                "duplicate_id": dup["id"],
                "external_id": canonical["external_id"] or dup["external_id"] or "N/A",
                "title": canonical["title"],
                "reason": (
                    f"Match {dup['id']} is duplicate of Match {canonical['id']} "
                    f"(external_id={canonical['external_id']!r}, slug={canonical['slug']!r}). "
                    f"Canonical row has specific URL {canonical['source_url']} and earlier creation."
                ),
            })
        print(f"    --> Selected CANONICAL: ID {canonical['id']} ({canonical['title']})")
        print(f"    --> Flagged DUPLICATES: {[d['id'] for d in duplicates]}")

    # 5. Run 188 ChangeEvents Investigation
    print("\n" + "=" * 80)
    print("--- 5. RUN 188 SPECIFIC AUDIT ---")
    cursor.execute("""
        SELECT id, started_at, finished_at, status, records_processed, changes_detected
        FROM scrape_runs
        WHERE id = 188;
    """)
    run_188 = cursor.fetchone()
    if run_188:
        print(f"  Run 188 Details: {dict(run_188)}")
    else:
        print("  Run 188 record not found in scrape_runs table.")

    # Find change events created during or around Run 188
    cursor.execute("""
        SELECT id, entity_type, entity_id, change_type, field_name, old_value, new_value, detected_at, notified_at
        FROM change_events
        ORDER BY id DESC
        LIMIT 20;
    """)
    recent_events = [dict(e) for e in cursor.fetchall()]
    print(f"\n  Latest 20 ChangeEvents in DB:")
    for ev in recent_events:
        is_dup_ref = ev["entity_id"] in all_duplicate_match_ids if ev["entity_type"] == "match" else False
        flag = " [REFERENCES DUPLICATE MATCH!]" if is_dup_ref else ""
        print(f"    - Event {ev['id']}: entity={ev['entity_type']} (ID {ev['entity_id']}), type={ev['change_type']}, field={ev['field_name']}, new={ev['new_value']!r}, detected_at={ev['detected_at']}{flag}")

    # 6. Migration Table
    print("\n" + "=" * 80)
    print("--- 6. PROPOSED MIGRATION TABLE (READ-ONLY PREVIEW) ---")
    print("=" * 80)
    if not proposed_pairs:
        print("  NO DUPLICATES FOUND. Database is completely clean.")
    else:
        print(f"| {'Canonical Match ID':<20} | {'Duplicate Match ID':<20} | {'External ID':<15} | {'Title':<35} | {'Reason':<60} |")
        print(f"|{'-'*22}|{'-'*22}|{'-'*17}|{'-'*37}|{'-'*62}|")
        for p in proposed_pairs:
            print(f"| {p['canonical_id']:<20} | {p['duplicate_id']:<20} | {p['external_id']:<15} | {p['title'][:35]:<35} | {p['reason'][:60]:<60} |")

    # 7. Proposed SQL Operations
    print("\n" + "=" * 80)
    print("--- 7. PROPOSED CLEANUP SQL STATEMENTS (DO NOT EXECUTE YET) ---")
    print("=" * 80)
    for p in proposed_pairs:
        c_id = p["canonical_id"]
        d_id = p["duplicate_id"]
        print(f"-- Step 1: Re-link ChangeEvents referencing duplicate Match {d_id} to Canonical Match {c_id}")
        print(f"UPDATE change_events SET entity_id = {c_id} WHERE entity_type = 'match' AND entity_id = {d_id};")
        print(f"-- Step 2: Delete duplicate Match row {d_id}")
        print(f"DELETE FROM matches WHERE id = {d_id};")
        print()

    print("=" * 80)
    print("AUDIT COMPLETE — NO MUTATIONS WERE PERFORMED ON THE DATABASE.")
    print("=" * 80 + "\n")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(run_audit())
