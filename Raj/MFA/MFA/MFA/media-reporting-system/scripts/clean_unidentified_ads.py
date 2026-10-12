"""
One-time cleanup: nullifies advertiser/brand fields that were stored as the
literal placeholder text 'Not identified' or 'Unknown placement', so the
identified_only filter works correctly across all three DB methods.

Run from project root:
    python scripts/clean_unidentified_ads.py
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.connection import get_db, get_db_path
from database.repository import utc_now_iso

def clean_placeholder_values():
    db_path = get_db_path()
    now = utc_now_iso()
    
    with get_db(db_path) as conn:
        # Nullify advertiser that is literal "Not identified"
        cur = conn.execute(
            "UPDATE advertisements SET advertiser = NULL, updated_at = ? "
            "WHERE LOWER(TRIM(advertiser)) IN ('not identified', 'unknown', 'n/a', '')",
            (now,)
        )
        adv_fixed = cur.rowcount
        
        # Nullify brand that is literal "Not identified"
        cur = conn.execute(
            "UPDATE advertisements SET brand = NULL, updated_at = ? "
            "WHERE LOWER(TRIM(brand)) IN ('not identified', 'unknown', 'n/a', '')",
            (now,)
        )
        brand_fixed = cur.rowcount
        
        # Nullify position that is literal "Unknown placement"  
        cur = conn.execute(
            "UPDATE advertisements SET position = 'UNKNOWN', updated_at = ? "
            "WHERE LOWER(TRIM(position)) IN ('unknown placement', 'unknown')",
            (now,)
        )
        pos_fixed = cur.rowcount
        
        # Stats
        row = conn.execute("SELECT COUNT(*) as total FROM advertisements").fetchone()
        total = row['total']
        
        row = conn.execute(
            "SELECT COUNT(*) as identified FROM advertisements WHERE "
            "((NULLIF(TRIM(brand), '') IS NOT NULL AND LOWER(TRIM(brand)) != 'not identified') OR "
            "(NULLIF(TRIM(advertiser), '') IS NOT NULL AND LOWER(TRIM(advertiser)) != 'not identified'))"
        ).fetchone()
        identified = row['identified']
    
    print("=" * 60)
    print("  Advertisement Database Cleanup Complete")
    print("=" * 60)
    print(f"  Advertiser fields nullified : {adv_fixed}")
    print(f"  Brand fields nullified      : {brand_fixed}")
    print(f"  Position fields normalized  : {pos_fixed}")
    print(f"  Total ads in DB             : {total}")
    print(f"  Verified/identified ads     : {identified}")
    print(f"  Hidden (unidentified) ads   : {total - identified}")
    print("=" * 60)
    print("  Restart the server to apply changes.")
    print("=" * 60)


if __name__ == "__main__":
    clean_placeholder_values()
