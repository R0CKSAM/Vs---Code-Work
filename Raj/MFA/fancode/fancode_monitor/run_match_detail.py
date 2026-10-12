"""
run_match_detail.py – CLI entrypoint for Match Detail Scraper.

Usage:
    python run_match_detail.py --limit 10
    python run_match_detail.py --url "https://www.fancode.com/matches/123"
    python run_match_detail.py --match-id 123
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from app.config.settings import settings
from app.database.connection import get_session
from app.database.models import Match
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Match Detail Scraper — Phase 5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=None, help="Specific match URL to enrich")
    parser.add_argument("--match-id", default=None, help="External ID of specific match to enrich")
    parser.add_argument("--limit", type=int, default=settings.MATCH_DETAIL_MAX_ITEMS,
                        help=f"Max batch matches to enrich (default: {settings.MATCH_DETAIL_MAX_ITEMS})")
    parser.add_argument("--timeout", type=int, default=settings.MATCH_DETAIL_TIMEOUT_SECONDS,
                        help=f"Timeout in seconds (default: {settings.MATCH_DETAIL_TIMEOUT_SECONDS})")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--no-db", action="store_true", help="Do not persist records to the database")

    args = parser.parse_args(argv)

    print("\n===========================================================")
    print("   FanCode Match Detail Scraper — Phase 5")
    print("===========================================================")
    print(f"  Mode       : {'HEADED' if args.headed else 'headless'}")
    print(f"  Timeout    : {args.timeout}s")
    print(f"  Persist DB : {not args.no_db}")
    print("===========================================================\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            scraper = FanCodeMatchDetailScraper(
                browser=browser,
                timeout_seconds=args.timeout,
            )

            if args.url:
                print(f"Enriching single match from URL: {args.url}")
                res = scraper.enrich_match_by_url(args.url, persist_db=not args.no_db)
                if res:
                    print(f"✅ Enriched: {res.title} | Venue: {res.venue or 'N/A'}")
            elif args.match_id:
                with get_session() as session:
                    match = session.query(Match).filter_by(external_id=args.match_id).first()
                if match:
                    print(f"Enriching match {args.match_id}: {match.source_url}")
                    res = scraper.enrich_match_by_url(match.source_url, persist_db=not args.no_db)
                    if res:
                        print(f"✅ Enriched: {res.title}")
                else:
                    print(f"❌ Match with external_id {args.match_id} not found in database.")
            else:
                print(f"Running batch enrichment (limit: {args.limit})...")
                results = scraper.enrich_batch(limit=args.limit, persist_db=not args.no_db)
                print(f"✅ Batch completed. Enriched {len(results)} matches.")

        finally:
            browser.close()

    print("\n===========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
