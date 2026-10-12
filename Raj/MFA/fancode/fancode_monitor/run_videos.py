"""
run_videos.py – CLI entrypoint for FanCode Videos & Highlights Scraper.

Usage:
    python run_videos.py
    python run_videos.py --max-items 20
    python run_videos.py --headed
    python run_videos.py --url "https://www.fancode.com/video"
    python run_videos.py --match-id "match-123"
    python run_videos.py --no-db
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
from app.scraper.videos.scraper import FanCodeVideosScraper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Videos & Highlights Scraper — Phase 7",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=settings.VIDEO_SCRAPER_URL,
                        help=f"Target videos URL (default: {settings.VIDEO_SCRAPER_URL})")
    parser.add_argument("--match-id", default=None,
                        help="Targeted match ID to discover associated video highlights")
    parser.add_argument("--max-items", type=int, default=settings.VIDEO_SCRAPER_MAX_ITEMS,
                        help=f"Maximum video items to collect (default: {settings.VIDEO_SCRAPER_MAX_ITEMS})")
    parser.add_argument("--timeout", type=int, default=settings.VIDEO_SCRAPER_TIMEOUT_SECONDS,
                        help=f"Timeout in seconds (default: {settings.VIDEO_SCRAPER_TIMEOUT_SECONDS})")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--save-raw", action="store_true", help="Save raw intercepted payloads to data/raw/videos")
    parser.add_argument("--no-db", action="store_true", help="Do not persist records to the database")

    args = parser.parse_args(argv)

    target_url = args.url
    if args.match_id:
        target_url = f"https://www.fancode.com/matches/{args.match_id}"

    print("\n===========================================================")
    print("   FanCode Videos & Highlights Scraper — Phase 7")
    print("===========================================================")
    print(f"  Target URL : {target_url}")
    if args.match_id:
        print(f"  Target Match: {args.match_id}")
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
            scraper = FanCodeVideosScraper(
                browser=browser,
                video_url=target_url,
                timeout_seconds=args.timeout,
                max_items=args.max_items,
                save_raw=args.save_raw,
            )
            records = scraper.scrape(persist_db=not args.no_db)

            print(f"\nDiscovered & Processed {len(records)} video records:")
            for i, rec in enumerate(records, 1):
                dur = f" ({rec.duration_seconds}s)" if rec.duration_seconds else ""
                match_info = f" | Match: {rec.match_external_id}" if rec.match_external_id else ""
                print(f"  [{i:02d}] [{rec.video_type}] {rec.title}{dur}{match_info}")
                if rec.source_url:
                    print(f"       URL: {rec.source_url}")

            print(f"\n✅ Completed successfully: {len(records)} video items processed.")

        except Exception as exc:
            print(f"\n❌ Scraper encountered an error: {exc}")
            return 1
        finally:
            browser.close()

    print("\n===========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
