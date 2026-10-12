"""
Phase 7.2 - Live Publication Time & Ad Creative Capture Diagnostics
Audits live publication timestamps and advertisement creative captures across
ET BrandEquity and Exchange4media without fabricating data.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Setup paths
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bs4 import BeautifulSoup
from database.connection import get_db, get_db_path
from scraper.base.fetcher import PageFetcher
from scraper.et_brand_equity.scraper import ETBrandEquityScraper
from scraper.exchange4media.scraper import Exchange4mediaScraper
from scraper.advertisements import AdvertisementDetector
from scraper.ad_image_storage import download_ad_image, save_ad_screenshot
from scraper.utils.date_parser import extract_publication_time_with_method, parse_date_to_iso

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def run_publication_time_audit():
    print("=" * 80)
    print("  PART B: LIVE PUBLICATION TIME EXTRACTION AUDIT (10 ARTICLES PER PUBLISHER)")
    print("=" * 80)

    fetcher = PageFetcher()
    results = {"et_brand_equity": [], "exchange4media": []}

    # 1. ET BrandEquity
    print("\n[1/2] Auditing ET BrandEquity Articles...")
    et_scraper = ETBrandEquityScraper()
    et_html = fetcher.fetch("https://brandequity.economictimes.indiatimes.com/")
    if et_html:
        articles, _, _ = et_scraper.extract_articles_from_html(et_html, "https://brandequity.economictimes.indiatimes.com/")
        sample = articles[:10]
        for i, art in enumerate(sample, 1):
            # Fetch article page to verify full metadata
            art_html = fetcher.fetch(art.url)
            if art_html:
                soup = BeautifulSoup(art_html, "html.parser")
                iso, method = extract_publication_time_with_method(soup)
            else:
                iso, method = art.published_at, ("FEED_CARD" if art.published_at else "UNAVAILABLE")

            entry = {
                "idx": i,
                "publisher": "ET BrandEquity",
                "headline": art.headline[:45] + ("..." if len(art.headline) > 45 else ""),
                "url": art.url,
                "published_at": iso or "None",
                "scraped_at": art.scraped_at or datetime.now(timezone.utc).isoformat(),
                "method": method,
            }
            results["et_brand_equity"].append(entry)
            print(f"  {i}. [{method}] {entry['headline']}")
            print(f"     URL: {art.url}")
            print(f"     Published: {entry['published_at']} | Scraped: {entry['scraped_at']}")

    # 2. Exchange4media
    print("\n[2/2] Auditing Exchange4media Articles...")
    e4m_scraper = Exchange4mediaScraper()
    e4m_html = fetcher.fetch("https://www.exchange4media.com/")
    if e4m_html:
        articles, _, _ = e4m_scraper.extract_articles_from_html(e4m_html, "https://www.exchange4media.com/")
        sample = articles[:10]
        for i, art in enumerate(sample, 1):
            art_html = fetcher.fetch(art.url)
            if art_html:
                soup = BeautifulSoup(art_html, "html.parser")
                iso, method = extract_publication_time_with_method(soup)
            else:
                iso, method = art.published_at, ("FEED_CARD" if art.published_at else "UNAVAILABLE")

            entry = {
                "idx": i,
                "publisher": "Exchange4media",
                "headline": art.headline[:45] + ("..." if len(art.headline) > 45 else ""),
                "url": art.url,
                "published_at": iso or "None",
                "scraped_at": art.scraped_at or datetime.now(timezone.utc).isoformat(),
                "method": method,
            }
            results["exchange4media"].append(entry)
            print(f"  {i}. [{method}] {entry['headline']}")
            print(f"     URL: {art.url}")
            print(f"     Published: {entry['published_at']} | Scraped: {entry['scraped_at']}")

    return results


def run_ad_capture_audit():
    print("\n" + "=" * 80)
    print("  PART K: LIVE ADVERTISEMENT DETECTION & EXACT CREATIVE CAPTURE AUDIT")
    print("=" * 80)

    fetcher = PageFetcher()
    ad_results = []

    portals = [
        ("ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/"),
        ("Exchange4media", "exchange4media", "https://www.exchange4media.com/"),
    ]

    for pub_name, pub_key, url in portals:
        print(f"\nScanning live advertisements on {pub_name} ({url})...")
        detector = AdvertisementDetector(pub_key)
        html = fetcher.fetch(url)
        if not html:
            print(f"  [!] Could not fetch {url}")
            continue

        detected = detector.detect_advertisements_from_html(html, url)
        print(f"  --> Found {len(detected)} candidate ad placements on {pub_name}")

        sample_ads = detected[:4]
        for i, ad in enumerate(sample_ads, 1):
            local_path = None
            capture_method = "IMAGE_DOWNLOAD"
            if ad.image_url:
                local_path = download_ad_image(ad.image_url, pub_key, ad.ad_hash)
            elif ad.ad_type == "IFRAME":
                capture_method = "IFRAME_ELEMENT"
            else:
                capture_method = "CONTAINER_SLOT"

            now_iso = datetime.now(timezone.utc).isoformat()
            res_entry = {
                "idx": i,
                "publisher": pub_name,
                "page_url": ad.page_url,
                "ad_type": ad.ad_type,
                "placement": ad.position,
                "advertiser": ad.advertiser or "Not identified",
                "brand": ad.brand or "Not identified",
                "creative_url": ad.image_url or "Unavailable (Dynamic Frame)",
                "local_image_path": local_path or "No local image saved",
                "first_seen": now_iso,
                "last_seen": now_iso,
                "hash": ad.ad_hash[:16] + "...",
                "capture_method": capture_method,
            }
            ad_results.append(res_entry)
            print(f"  Ad {i}:")
            print(f"     Publisher:      {res_entry['publisher']}")
            print(f"     Placement:      {res_entry['placement']} ({res_entry['ad_type']})")
            print(f"     Identity:       {res_entry['brand']} (Adv: {res_entry['advertiser']})")
            print(f"     Creative URL:   {res_entry['creative_url']}")
            print(f"     Local Asset:    {res_entry['local_image_path']}")
            print(f"     Capture Method: {res_entry['capture_method']}")
            print(f"     Ad Hash:        {res_entry['hash']}")

    return ad_results


if __name__ == "__main__":
    run_publication_time_audit()
    run_ad_capture_audit()
