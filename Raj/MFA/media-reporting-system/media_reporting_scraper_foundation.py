"""
Media Reporting System - Scraper Foundation (Phase 2A: ET BrandEquity)
=====================================================================

CLI Entrypoint for running the ET BrandEquity article scraper.

Usage:
    python media_reporting_scraper_foundation.py --site et_brand_equity --mode homepage --no-browser-fallback

Options:
    --site: Website to scrape ('et_brand_equity', 'exchange4media', 'all')
    --mode: Scrape mode ('homepage', 'sections')
    --no-browser-fallback: Disable Playwright fallback (Requests only)
    --delay: Polite delay between requests in seconds (default: 2.0)
    --enrich: Fetch article pages to enrich missing summaries and publication timestamps
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path so 'scraper' package can be imported directly
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.base.article import Article
from scraper.et_brand_equity.config import ET_BRAND_EQUITY
from scraper.et_brand_equity.scraper import ETBrandEquityScraper
from scraper.exchange4media.config import EXCHANGE4MEDIA
from scraper.exchange4media.scraper import Exchange4mediaScraper
from scraper.campaign_india.config import CAMPAIGN_INDIA
from scraper.campaign_india.scraper import CampaignIndiaScraper
from scraper.bestmediainfo.config import BESTMEDIAINFO
from scraper.bestmediainfo.scraper import BestMediaInfoScraper
from scraper.social_samosa.config import SOCIAL_SAMOSA
from scraper.social_samosa.scraper import SocialSamosaScraper
from scraper.adgully.config import ADGULLY
from scraper.adgully.scraper import AdgullyScraper
from scraper.mediabrief.config import MEDIABRIEF
from scraper.mediabrief.scraper import MediaBriefScraper
from scraper.storyboard18.config import STORYBOARD18
from scraper.storyboard18.scraper import Storyboard18Scraper
from scraper.indiantelevision.config import INDIAN_TELEVISION
from scraper.indiantelevision.scraper import IndianTelevisionScraper

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("media-scraper")

OUTPUT_DIR = PROJECT_ROOT / "scraper_output"


# ---------------------------------------------------------------------------
# JSON Persistence
# ---------------------------------------------------------------------------
def save_output_json(articles: list[Article], website_key: str) -> Path:
    """Saves normalized articles to scraper_output/<website_key>.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{website_key}.json"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "website": website_key,
        "count": len(articles),
        "articles": [asdict(a) for a in articles],
    }

    output_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_file


# ---------------------------------------------------------------------------
# Quality Report & Summary Printing
# ---------------------------------------------------------------------------
def print_quality_report(articles: list[Article], stats: dict, website_name: str = "ET BrandEquity") -> None:
    """Prints the comprehensive data quality report for the target website."""
    total = len(articles)

    has_headline = sum(1 for a in articles if a.headline)
    has_url = sum(1 for a in articles if a.url)
    has_image = sum(1 for a in articles if a.image_url)
    has_summary = sum(1 for a in articles if a.summary)
    has_published_at = sum(1 for a in articles if a.published_at)
    has_section = sum(1 for a in articles if a.section and a.section != "Overall")
    has_hash = sum(1 for a in articles if a.content_hash)

    section_counts = Counter(a.section for a in articles)

    print()
    print("=" * 80)
    print(f"{website_name.upper()} SCRAPER — DATA QUALITY REPORT")
    print("=" * 80)
    print(f"Website:             {website_name}")
    print(f"Pages fetched:       {stats.get('pages_fetched', 1)}")
    print(f"Article candidates:  {stats.get('candidates', total)}")
    print(f"Valid articles:      {total}")
    print(f"Duplicates removed:  {stats.get('duplicates_removed', 0)}")
    print("-" * 80)
    print("Articles with verified fields:")

    def pct(count: int) -> str:
        return f"{count} / {total} ({(count / total * 100) if total else 0:.1f}%)"

    print(f"  - Headline:        {pct(has_headline)}")
    print(f"  - URL:             {pct(has_url)}")
    print(f"  - Image:           {pct(has_image)}")
    print(f"  - Summary:         {pct(has_summary)}")
    print(f"  - Published At:    {pct(has_published_at)}")
    print(f"  - Specific Section:{pct(has_section)}")
    print(f"  - Content Hash:    {pct(has_hash)}")
    print("-" * 80)
    print("Section Distribution:")
    for sec, count in sorted(section_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {sec:<24}: {count}")
    print("=" * 80)
    print()

    # Print sample of 10 articles
    sample_size = min(10, total)
    print(f"SAMPLE OF {sample_size} EXTRACTED ARTICLES:")
    print("-" * 80)
    for idx, art in enumerate(articles[:sample_size], start=1):
        print(f"[{idx}] {art.headline}")
        print(f"    Section     : {art.section}")
        print(f"    Published At: {art.published_at or 'null'}")
        print(f"    URL         : {art.url}")
        print(f"    Image       : {art.image_url or 'null'}")
        print(f"    Summary     : {art.summary or 'null'}")
        print(f"    Hash        : {art.content_hash[:16]}...")
        print()
    print("=" * 80)


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Media Reporting System - Multi-Portal Article Scraper"
    )
    parser.add_argument(
        "--site",
        choices=[
            "et_brand_equity",
            "exchange4media",
            "campaign_india",
            "bestmediainfo",
            "social_samosa",
            "adgully",
            "mediabrief",
            "storyboard18",
            "indiantelevision",
            "all",
        ],
        default="all",
        help="Target site to scrape.",
    )
    parser.add_argument(
        "--mode",
        choices=["homepage", "sections"],
        default="homepage",
        help="Scrape homepage or specific configured sections.",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="Disable Playwright fallback (pure Requests + BeautifulSoup).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Polite request delay between page queries in seconds.",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich top articles by fetching individual article pages.",
    )
    parser.add_argument(
        "--max-enrich",
        type=int,
        default=10,
        help="Maximum number of articles to enrich when --enrich is enabled (default: 10).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Execution Handlers
# ---------------------------------------------------------------------------
def run_et_brand_equity(args: argparse.Namespace) -> list[Article]:
    logger.info("Initializing ET BrandEquity Article Scraper...")
    scraper = ETBrandEquityScraper(
        config=ET_BRAND_EQUITY,
        delay_seconds=args.delay,
        browser_fallback=not args.no_browser_fallback,
    )

    if args.mode == "homepage":
        articles, stats = scraper.scrape_homepage(
            enrich=args.enrich,
            max_enrich=args.max_enrich,
        )
    else:
        logger.info("Scraping configured sections for ET BrandEquity...")
        all_articles: list[Article] = []
        total_candidates = 0
        total_duplicates = 0
        pages_fetched = 0

        for section_cfg in ET_BRAND_EQUITY.sections:
            logger.info("Fetching section [%s]: %s", section_cfg.name, section_cfg.url)
            html = scraper.fetcher.fetch(section_cfg.url, browser_fallback=not args.no_browser_fallback)
            pages_fetched += 1
            if html:
                arts, cands, dups = scraper.extract_articles_from_html(
                    html,
                    page_url=section_cfg.url,
                    default_section=section_cfg.name,
                )
                all_articles.extend(arts)
                total_candidates += cands
                total_duplicates += dups

        articles, dups_removed = scraper.deduplicate_articles(all_articles)
        stats = {
            "pages_fetched": pages_fetched,
            "candidates": total_candidates,
            "valid_articles": len(articles),
            "duplicates_removed": total_duplicates + dups_removed,
        }

    output_path = save_output_json(articles, "et_brand_equity")
    print_quality_report(articles, stats, website_name="ET BrandEquity")
    logger.info("ET BrandEquity scrape complete. Saved %d verified articles to %s", len(articles), output_path)
    return articles


def run_exchange4media(args: argparse.Namespace) -> list[Article]:
    logger.info("Initializing Exchange4media Article Scraper (Phase 3)...")
    scraper = Exchange4mediaScraper(
        config=EXCHANGE4MEDIA,
        delay_seconds=args.delay,
        browser_fallback=not args.no_browser_fallback,
    )

    if args.mode == "homepage":
        articles, stats = scraper.scrape_homepage(
            enrich=args.enrich,
            max_enrich=args.max_enrich,
        )
    else:
        logger.info("Scraping configured sections for Exchange4media...")
        all_articles: list[Article] = []
        total_candidates = 0
        total_duplicates = 0
        pages_fetched = 0

        for section_cfg in EXCHANGE4MEDIA.sections:
            logger.info("Fetching section [%s]: %s", section_cfg.name, section_cfg.url)
            html = scraper.fetcher.fetch(section_cfg.url, browser_fallback=not args.no_browser_fallback)
            pages_fetched += 1
            if html:
                arts, cands, dups = scraper.extract_articles_from_html(
                    html,
                    page_url=section_cfg.url,
                    default_section=section_cfg.name,
                )
                all_articles.extend(arts)
                total_candidates += cands
                total_duplicates += dups

        articles, dups_removed = scraper.deduplicate_articles(all_articles)
        stats = {
            "pages_fetched": pages_fetched,
            "candidates": total_candidates,
            "valid_articles": len(articles),
            "duplicates_removed": total_duplicates + dups_removed,
        }

    output_path = save_output_json(articles, "exchange4media")
    print_quality_report(articles, stats, website_name="Exchange4media")
    logger.info("Exchange4media scrape complete. Saved %d verified articles to %s", len(articles), output_path)
    return articles


def run_generic_site(args: argparse.Namespace, scraper_cls, config, key: str, name: str) -> list[Article]:
    scraper = scraper_cls(
        config=config,
        delay_seconds=args.delay,
        browser_fallback=not args.no_browser_fallback,
    )
    articles, stats = scraper.scrape_homepage(
        enrich=args.enrich,
        max_enrich=args.max_enrich,
    )
    output_path = save_output_json(articles, key)
    print_quality_report(articles, stats, website_name=name)
    logger.info("%s scrape complete. Saved %d verified articles to %s", name, len(articles), output_path)
    return articles


def main() -> None:
    args = parse_args()

    dispatch = {
        "et_brand_equity": lambda: run_et_brand_equity(args),
        "exchange4media": lambda: run_exchange4media(args),
        "campaign_india": lambda: run_generic_site(args, CampaignIndiaScraper, CAMPAIGN_INDIA, "campaign_india", "Campaign India"),
        "bestmediainfo": lambda: run_generic_site(args, BestMediaInfoScraper, BESTMEDIAINFO, "bestmediainfo", "BestMediaInfo"),
        "social_samosa": lambda: run_generic_site(args, SocialSamosaScraper, SOCIAL_SAMOSA, "social_samosa", "Social Samosa"),
        "adgully": lambda: run_generic_site(args, AdgullyScraper, ADGULLY, "adgully", "Adgully"),
        "mediabrief": lambda: run_generic_site(args, MediaBriefScraper, MEDIABRIEF, "mediabrief", "MediaBrief"),
        "storyboard18": lambda: run_generic_site(args, Storyboard18Scraper, STORYBOARD18, "storyboard18", "Storyboard18"),
        "indiantelevision": lambda: run_generic_site(args, IndianTelevisionScraper, INDIAN_TELEVISION, "indiantelevision", "Indian Television"),
    }

    if args.site in dispatch:
        dispatch[args.site]()
    elif args.site == "all":
        for fn in dispatch.values():
            fn()


if __name__ == "__main__":
    main()

