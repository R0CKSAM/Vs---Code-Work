"""
Media Reporting System - Standalone CLI for Gmail Sync & Reports
Runs directly with standard Python - ZERO external dependencies required for Gmail IMAP!
Can also seed sample data and export reports to CSV or Excel directly from terminal.
"""
import os
import sys
from pathlib import Path

# Ensure paths
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for _p in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database.schema import init_db
from mailer.gmail_fetcher import GmailMailerFetcher
from mailer.service import mailer_service
from mailer.export import mailer_exporter


def run_gmail_sync():
    print("=" * 65)
    print("  MEDIA REPORTING — GMAIL NEWSLETTER INGESTION CLI")
    print("=" * 65)
    
    # 1. Initialize DB
    print("[1/3] Initializing database schema...")
    init_db()

    email_addr = "rajxy101@gmail.com"
    app_pwd = "mqkvthzywlkfwudg"

    print(f"[2/3] Connecting to Gmail IMAP (imap.gmail.com:993) for {email_addr}...")
    fetcher = GmailMailerFetcher(email_address=email_addr, app_password=app_pwd)
    
    try:
        # Search query for BestMediaInfo
        res = fetcher.fetch_and_ingest(
            search_query='(OR FROM "bestmediainfo" SUBJECT "BestMediaInfo")',
            max_emails=10,
        )
        print(f"[3/3] Sync Result: {res.get('message')}")
        print("-" * 65)
        print(f"  • Emails checked: {res.get('checked_count')}")
        print(f"  • Newly imported: {res.get('ingested_count')}")
        print(f"  • Duplicates skipped: {res.get('duplicate_count')}")
        print("-" * 65)

        for item in res.get("results", []):
            print(f"  -> [{item.get('status')}] {item.get('subject')}")
            print(f"     Articles: {item.get('article_count')} | Ads: {item.get('advertisement_count')}")

    except Exception as exc:
        print(f"\n[!] Gmail Fetch Failed: {exc}")
        print("\n[Tip] You can still test parser & DB by seeding sample:")
        print("      python sync_gmail.py --sample")


def run_sample_seed():
    print("=" * 65)
    print("  MEDIA REPORTING — SEED SAMPLE BEST MEDIA INFO NEWSLETTER")
    print("=" * 65)
    init_db()
    fixture_path = PROJECT_ROOT / "mailer" / "tests" / "fixtures" / "best_media_info_sample.html"
    if not fixture_path.exists():
        print(f"[!] Fixture not found at {fixture_path}")
        return

    meta = {
        "sender_name": "Best Media Info",
        "sender_email": "bmi@bestmediainfo.in",
        "date": "2026-10-06T11:34:00",
    }
    result = mailer_service.process_file(fixture_path, metadata=meta)
    print(f"Status: {result.get('status')}")
    print(f"Articles Extracted: {result.get('article_count')}")
    print(f"Advertisements Extracted: {result.get('advertisement_count')}")

    # Export to CSV
    detail = result.get("data")
    if detail:
        csv_file = mailer_exporter.export_csv(detail, "sample_bestmediainfo.csv")
        print(f"Exported CSV: {csv_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        run_sample_seed()
    else:
        run_gmail_sync()
