"""
scripts/audit_run216.py – Read-only Forensic Audit of Production Run 216.
Zero mutations are performed on the database.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fancode.db"
OUTPUT_FILE = ROOT / "data" / "run216_forensic_report.json"

def main():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} does not exist")
        return 1

    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    report = {}

    # 1. PRAGMAs & Table Counts
    cur.execute("PRAGMA integrity_check;")
    report["integrity_check"] = [r[0] for r in cur.fetchall()]

    cur.execute("PRAGMA foreign_key_check;")
    report["foreign_key_check"] = [dict(r) for r in cur.fetchall()]

    tables = [
        "sports", "tours", "matches", "videos", "pages",
        "change_events", "scrape_runs", "notification_batches",
        "notification_deliveries", "notification_event_links"
    ]
    report["counts"] = {t: cur.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0] for t in tables}

    # 2. Scrape Runs (Runs >= 215)
    cur.execute("SELECT * FROM scrape_runs WHERE id >= 215 ORDER BY id ASC;")
    report["scrape_runs_215_plus"] = [dict(r) for r in cur.fetchall()]

    # 3. All Matches (1 to 25)
    cur.execute("SELECT * FROM matches ORDER BY id ASC;")
    report["all_matches"] = [dict(r) for r in cur.fetchall()]

    # 4. Matches 21 to 25 specifically
    cur.execute("""
        SELECT m.*, t.name as tour_name, t.slug as tour_slug, s.name as sport_name
        FROM matches m
        LEFT JOIN tours t ON m.tour_id = t.id
        LEFT JOIN sports s ON m.sport_id = s.id
        WHERE m.id >= 21
        ORDER BY m.id ASC;
    """)
    report["new_matches_21_25"] = [dict(r) for r in cur.fetchall()]

    # 5. Tours (All 6 tours)
    cur.execute("SELECT * FROM tours ORDER BY id ASC;")
    report["all_tours"] = [dict(r) for r in cur.fetchall()]

    # 6. Change Events (All >= 26)
    cur.execute("SELECT * FROM change_events WHERE id >= 26 ORDER BY id ASC;")
    report["new_change_events"] = [dict(r) for r in cur.fetchall()]

    # 7. Notification Batches & Deliveries & Links (Batch >= 4)
    cur.execute("SELECT * FROM notification_batches WHERE id >= 4 ORDER BY id ASC;")
    report["notification_batches"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM notification_deliveries WHERE id >= 4 ORDER BY id ASC;")
    report["notification_deliveries"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM notification_event_links WHERE id >= 26 ORDER BY id ASC;")
    report["notification_event_links"] = [dict(r) for r in cur.fetchall()]

    # 8. Check external_id 4249664 and other investigated IDs
    target_ids = ['4249664', '4248813', '4248814', '4248815', '4248816', '4250124', '4250055', '4250088']
    cur.execute(f"SELECT * FROM matches WHERE external_id IN ({','.join(['?']*len(target_ids))}) OR id = 17;", target_ids)
    report["target_matches"] = [dict(r) for r in cur.fetchall()]

    # 9. Duplicate external IDs check
    cur.execute("""
        SELECT external_id, COUNT(*) as cnt, GROUP_CONCAT(id) as match_ids
        FROM matches
        WHERE external_id IS NOT NULL
        GROUP BY external_id
        HAVING cnt > 1;
    """)
    report["duplicate_external_ids"] = [dict(r) for r in cur.fetchall()]

    # 10. Null external IDs check
    cur.execute("SELECT id, title, slug, source_url FROM matches WHERE external_id IS NULL;")
    report["null_external_ids"] = [dict(r) for r in cur.fetchall()]

    conn.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Wrote forensic report to {OUTPUT_FILE}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
