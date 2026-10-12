"""
__main__.py – CLI entrypoint for the FanCode Discovery Engine.

Usage:
    python -m app.scraper.discovery
    python -m app.scraper.discovery --max-pages 10 --depth 1
    python -m app.scraper.discovery --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is importable when run as a module
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from app.config.settings import settings
from app.scraper.discovery.crawler import FanCodeCrawler, save_discovery_result
from app.scraper.discovery.report_generator import generate_report


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FanCode Discovery Engine – Phase 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--seed-url",  default=settings.BASE_URL,
                        help=f"Starting URL (default: {settings.BASE_URL})")
    parser.add_argument("--max-pages", type=int, default=settings.DISCOVERY_MAX_PAGES,
                        help=f"Max pages to visit (default: {settings.DISCOVERY_MAX_PAGES})")
    parser.add_argument("--depth",     type=int, default=settings.DISCOVERY_MAX_DEPTH,
                        help=f"Max crawl depth (default: {settings.DISCOVERY_MAX_DEPTH})")
    parser.add_argument("--max-links", type=int, default=settings.DISCOVERY_MAX_LINKS_PER_PAGE,
                        help=f"Max links per page (default: {settings.DISCOVERY_MAX_LINKS_PER_PAGE})")
    parser.add_argument("--timeout",   type=int, default=settings.DISCOVERY_TIMEOUT_SECONDS,
                        help=f"Total wall-clock timeout in seconds (default: {settings.DISCOVERY_TIMEOUT_SECONDS})")
    parser.add_argument("--delay",     type=float, default=settings.REQUEST_DELAY_SECONDS,
                        help=f"Delay between page visits in seconds (default: {settings.REQUEST_DELAY_SECONDS})")
    parser.add_argument("--output-dir", default=settings.DISCOVERY_OUTPUT_DIR,
                        help=f"Artifact output directory (default: {settings.DISCOVERY_OUTPUT_DIR})")
    parser.add_argument("--save-db", action="store_true",
                        help="Persist discovered pages to the database")
    parser.add_argument("--report",    default="docs/discovery.md",

                        help="Path for the discovery report (default: docs/discovery.md)")
    parser.add_argument("--log-level", default=settings.LOG_LEVEL,
                        help=f"Logging level (default: {settings.LOG_LEVEL})")
    parser.add_argument("--headed",    action="store_true",
                        help="Run Chromium in headed (visible) mode")

    args = parser.parse_args(argv)
    _setup_logging(args.log_level)
    logger = logging.getLogger("discovery.main")

    print("\n" + "=" * 60)
    print("  FanCode Discovery Engine — Phase 1")
    print("=" * 60)
    print(f"  Seed URL   : {args.seed_url}")
    print(f"  Max pages  : {args.max_pages}")
    print(f"  Max depth  : {args.depth}")
    print(f"  Max links  : {args.max_links}")
    print(f"  Timeout    : {args.timeout}s")
    print(f"  Delay      : {args.delay}s between pages")
    print(f"  Mode       : {'HEADED' if args.headed else 'headless'}")
    print(f"  Output dir : {args.output_dir}")
    print("=" * 60 + "\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            crawler = FanCodeCrawler(
                browser=browser,
                max_pages=args.max_pages,
                max_depth=args.depth,
                max_links_per_page=args.max_links,
                timeout_seconds=args.timeout,
                delay_seconds=args.delay,
                seed_url=args.seed_url,
            )
            result = crawler.run()
        finally:
            browser.close()

    # Save JSON artifact
    artifact_path = save_discovery_result(result, args.output_dir)
    print(f"\n  Artifact saved : {artifact_path}")

    # Optionally persist to database
    if args.save_db:
        from app.scraper.discovery.crawler import persist_discovery_to_db
        count = persist_discovery_to_db(result)
        print(f"  Database saved : {count} pages persisted/updated")

    # Generate markdown report

    report_path = generate_report(result, args.report)
    print(f"  Report saved   : {report_path}")

    # Summary
    print("\n" + "-" * 60)
    print(f"  Pages visited  : {result.page_count}")
    print(f"  JSON endpoints : {len(result.json_endpoints)}")
    print(f"  Network events : {len(result.all_network_events)}")
    if result.terminated_early:
        print(f"  Terminated early: {result.termination_reason}")
    for ptype, pages in result.pages_by_type.items():
        print(f"    {ptype:12s}: {len(pages)} page(s)")
    print("-" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
