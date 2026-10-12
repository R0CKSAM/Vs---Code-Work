"""
Media Reporting System - Initial Database Seeding & Baseline Import
Initializes SQLite schema and imports verified Phase 3.2 scraper outputs into the database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.schema import init_db, init_schema
from database.repository import db_repo

try:
    from app.services.change_detector import change_detector
except ImportError:
    from backend.app.services.change_detector import change_detector


def seed_baseline() -> dict:
    print("=" * 70)
    print("  PHASE 4: INITIALIZING DATABASE & SEEDING BASELINE DATA")
    print("=" * 70)

    # 1. Initialize schema
    print("\n[1/3] Initializing SQLite schema (websites, sections, articles, versions, scrape_runs)...")
    init_db()
    print("      --> Schema initialized successfully.")

    results = {}

    # 2. Seed ET BrandEquity baseline
    et_json_path = PROJECT_ROOT / "scraper_output" / "et_brand_equity.json"
    if et_json_path.exists():
        print(f"\n[2/3] Seeding ET BrandEquity from: {et_json_path.name}...")
        data = json.loads(et_json_path.read_text(encoding="utf-8"))
        articles = data.get("articles", [])
        et_res = change_detector.process_scraped_articles("et_brand_equity", articles)
        results["et_brand_equity"] = et_res
        print(f"      --> Processed {et_res['items_found']} articles: "
              f"{et_res['new_items']} NEW, {et_res['updated_items']} UPDATED, "
              f"{et_res['unchanged_items']} UNCHANGED, {et_res['removed_items']} REMOVED.")
    else:
        print(f"[!] Warning: {et_json_path} not found.")

    # 3. Seed Exchange4media baseline
    e4m_json_path = PROJECT_ROOT / "scraper_output" / "exchange4media.json"
    if e4m_json_path.exists():
        print(f"\n[3/3] Seeding Exchange4media from: {e4m_json_path.name}...")
        data = json.loads(e4m_json_path.read_text(encoding="utf-8"))
        articles = data.get("articles", [])
        e4m_res = change_detector.process_scraped_articles("exchange4media", articles)
        results["exchange4media"] = e4m_res
        print(f"      --> Processed {e4m_res['items_found']} articles: "
              f"{e4m_res['new_items']} NEW, {e4m_res['updated_items']} UPDATED, "
              f"{e4m_res['unchanged_items']} UNCHANGED, {e4m_res['removed_items']} REMOVED.")
    else:
        print(f"[!] Warning: {e4m_json_path} not found.")

    print("\n" + "=" * 70)
    print("  INITIAL SEEDING COMPLETE")
    print("=" * 70)
    return results


if __name__ == "__main__":
    seed_baseline()
