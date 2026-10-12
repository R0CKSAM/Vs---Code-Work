"""
scripts/diagnose_collisions.py – Read-only diagnosis of match records and URL extraction.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.discovery.url_normalizer import extract_match_id_from_url

DB_PATH = ROOT / "data" / "fancode.db"

def main():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} does not exist")
        return 1

    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, slug, source_url, external_id, status, start_time, match_date, team_a_name, team_b_name, venue, last_seen_at
        FROM matches
        ORDER BY id ASC;
    """)
    all_matches = [dict(r) for r in cur.fetchall()]

    print("=" * 100)
    print(f"TOTAL MATCHES IN DATABASE: {len(all_matches)}")
    print("=" * 100)
    print(f"{'ID':<4} | {'Ext ID':<8} | {'Title':<32} | {'Slug':<28} | {'Extracted ID':<14} | {'Source URL'}")
    print("-" * 120)

    for m in all_matches:
        ext_id = extract_match_id_from_url(m["source_url"])
        print(f"{m['id']:<4} | {str(m['external_id']):<8} | {m['title'][:32]:<32} | {m['slug'][:28]:<28} | {str(ext_id):<14} | {m['source_url']}")

    print("\n" + "=" * 100)
    print("DETAILED INSPECTION OF COLLISION CANDIDATES (10, 11, 14, 15)")
    print("=" * 100)
    for m in all_matches:
        if m["id"] in (10, 11, 14, 15):
            ext_id = extract_match_id_from_url(m["source_url"])
            print(f"\n--- MATCH ID: {m['id']} ---")
            print(f"  Title        : {m['title']}")
            print(f"  Slug         : {m['slug']}")
            print(f"  Source URL   : {m['source_url']}")
            print(f"  Extracted ID : {ext_id}")
            print(f"  Status       : {m['status']}")
            print(f"  Start Time   : {m['start_time']}")
            print(f"  Match Date   : {m['match_date']}")
            print(f"  Team A       : {m['team_a_name']}")
            print(f"  Team B       : {m['team_b_name']}")
            print(f"  Venue        : {m['venue']}")
            print(f"  Last Seen At : {m['last_seen_at']}")

    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
