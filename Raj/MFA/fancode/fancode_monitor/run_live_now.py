"""
run_live_now.py – CLI entrypoint for FanCode Live Now Scraper.

Usage:
    python run_live_now.py
    python run_live_now.py --max-items 20
    python run_live_now.py --headed
    python run_live_now.py --url "https://www.fancode.com/live"
    python run_live_now.py --no-db
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
from app.scraper.live_now.scraper import FanCodeLiveNowScraper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Live Now Scraper — Phase 6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=settings.LIVE_NOW_URL,
                        help=f"Live Now target URL (default: {settings.LIVE_NOW_URL})")
    parser.add_argument("--max-items", type=int, default=settings.LIVE_NOW_MAX_ITEMS,
                        help=f"Maximum live items to collect (default: {settings.LIVE_NOW_MAX_ITEMS})")
    parser.add_argument("--timeout", type=int, default=settings.LIVE_NOW_TIMEOUT_SECONDS,
                        help=f"Timeout in seconds (default: {settings.LIVE_NOW_TIMEOUT_SECONDS})")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--save-raw", action="store_true", help="Save raw intercepted payloads to data/raw/live_now")
    parser.add_argument("--no-db", action="store_true", help="Do not persist records to the database")

    args = parser.parse_args(argv)

    print("\n===========================================================")
    print("   FanCode Live Now Scraper — Phase 6")
    print("===========================================================")
    print(f"  Target URL : {args.url}")
    print(f"  Mode       : {'HEADED' if args.headed else 'headless'}")
    print(f"  Max items  : {args.max_items}")
    print(f"  Timeout    : {args.timeout}s")
    print(f"  Save Raw   : {args.save_raw}")
    print(f"  Persist DB : {not args.no_db}")
    print("===========================================================\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            scraper = FanCodeLiveNowScraper(
                browser=browser,
                live_url=args.url,
                timeout_seconds=args.timeout,
                max_items=args.max_items,
                save_raw=args.save_raw,
            )
            records = scraper.scrape(persist_db=not args.no_db)

            print(f"\nDiscovered & Processed {len(records)} live match records:")
            for i, rec in enumerate(records, 1):
                score = f" | Score: {rec.score_summary}" if rec.score_summary else ""
                print(f"  [{i:02d}] [{rec.status}] {rec.title}{score}")
                if rec.source_url:
                    print(f"       URL: {rec.source_url}")

            print(f"\n✅ Completed successfully: {len(records)} live items processed.")

        except Exception as exc:
            print(f"\n❌ Scraper encountered an error: {exc}")
            return 1
        finally:
            browser.close()

    print("\n===========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
