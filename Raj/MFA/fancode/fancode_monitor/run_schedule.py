"""
run_schedule.py – CLI entrypoint for FanCode Schedule Scraper.

Usage:
    python run_schedule.py
    python run_schedule.py --headed --max-items 20 --save-raw
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
from app.scraper.schedule.scraper import FanCodeScheduleScraper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Schedule Scraper — Phase 3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=settings.SCHEDULE_URL,
                        help=f"Target schedule URL (default: {settings.SCHEDULE_URL})")
    parser.add_argument("--max-items", type=int, default=settings.SCHEDULE_MAX_ITEMS,
                        help=f"Max items to scrape (default: {settings.SCHEDULE_MAX_ITEMS})")
    parser.add_argument("--timeout", type=int, default=settings.SCHEDULE_TIMEOUT_SECONDS,
                        help=f"Timeout in seconds (default: {settings.SCHEDULE_TIMEOUT_SECONDS})")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed mode")
    parser.add_argument("--no-db", action="store_true",
                        help="Do not persist records to the database")
    parser.add_argument("--save-raw", action="store_true",
                        help="Save raw network payloads to data/raw/schedule/")

    args = parser.parse_args(argv)

    print("\n===========================================================")
    print("   FanCode Schedule Scraper — Phase 3")
    print("===========================================================")
    print(f"  URL        : {args.url}")
    print(f"  Max items  : {args.max_items}")
    print(f"  Timeout    : {args.timeout}s")
    print(f"  Mode       : {'HEADED' if args.headed else 'headless'}")
    print(f"  Persist DB : {not args.no_db}")
    print(f"  Save Raw   : {args.save_raw}")
    print("===========================================================\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            scraper = FanCodeScheduleScraper(
                browser=browser,
                schedule_url=args.url,
                max_items=args.max_items,
                timeout_seconds=args.timeout,
                save_raw=args.save_raw,
            )
            matches = scraper.scrape(persist_db=not args.no_db)
        finally:
            browser.close()

    print("\n-----------------------------------------------------------")
    print(f"✅ Scraping completed. Retrieved {len(matches)} matches.")
    for i, m in enumerate(matches[:10], 1):
        print(f"   {i}. [{m.status}] {m.title} ({m.sport_name or 'Unknown Sport'})")
    if len(matches) > 10:
        print(f"   ... and {len(matches) - 10} more.")
    print("-----------------------------------------------------------\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
