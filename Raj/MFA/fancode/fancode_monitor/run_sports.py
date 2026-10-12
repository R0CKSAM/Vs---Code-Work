"""
run_sports.py – CLI entrypoint for FanCode Sports Scraper.

Usage:
    python run_sports.py
    python run_sports.py --headed --max-items 20
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
from app.scraper.sports.scraper import FanCodeSportsScraper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Sports Scraper — Phase 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=settings.SPORTS_URL,
                        help=f"Target sports URL (default: {settings.SPORTS_URL})")
    parser.add_argument("--max-items", type=int, default=settings.SPORT_MAX_ITEMS,
                        help=f"Max sports to scrape (default: {settings.SPORT_MAX_ITEMS})")
    parser.add_argument("--timeout", type=int, default=settings.SPORT_TIMEOUT_SECONDS,
                        help=f"Timeout in seconds (default: {settings.SPORT_TIMEOUT_SECONDS})")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed mode")
    parser.add_argument("--no-db", action="store_true",
                        help="Do not persist records to the database")
    parser.add_argument("--save-raw", action="store_true",
                        help="Save raw network payloads to data/raw/sports/")

    args = parser.parse_args(argv)

    print("\n===========================================================")
    print("   FanCode Sports Scraper — Phase 4")
    print("===========================================================")
    print(f"  URL        : {args.url}")
    print(f"  Max items  : {args.max_items}")
    print(f"  Timeout    : {args.timeout}s")
    print(f"  Mode       : {'HEADED' if args.headed else 'headless'}")
    print(f"  Persist DB : {not args.no_db}")
    print("===========================================================\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            scraper = FanCodeSportsScraper(
                browser=browser,
                sports_url=args.url,
                max_items=args.max_items,
                timeout_seconds=args.timeout,
                save_raw=args.save_raw,
            )
            sports = scraper.scrape(persist_db=not args.no_db)
        finally:
            browser.close()

    print("\n-----------------------------------------------------------")
    print(f"✅ Scraping completed. Retrieved {len(sports)} sports:")
    for i, s in enumerate(sports, 1):
        print(f"   {i}. {s.name} (slug: {s.slug}) -> {s.source_url}")
    print("-----------------------------------------------------------\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
