"""
Media Reporting System - Live Media Extraction Diagnostic Utility
Fetches current live articles from ET BrandEquity and Exchange4media,
inspects all candidate publication-time sources, and prints diagnostic evidence.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List

# Setup sys.path for direct execution
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bs4 import BeautifulSoup
from scraper.base.fetcher import PageFetcher
from scraper.et_brand_equity.scraper import ETBrandEquityScraper
from scraper.exchange4media.scraper import Exchange4mediaScraper
from scraper.utils.date_parser import extract_publication_time_with_method

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("diagnostic")


def inspect_article_page(url: str, fetcher: PageFetcher) -> dict:
    """Inspects an article page for all publication date signals."""
    html = fetcher.fetch_requests(url)
    if not html:
        return {"url": url, "error": "Failed to fetch HTML"}

    soup = BeautifulSoup(html, "html.parser")
    headline_el = soup.find(["h1", "h2"])
    headline = headline_el.get_text(" ", strip=True) if headline_el else "Unknown Headline"

    # 1. Collect candidate meta tags
    meta_candidates = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name") or meta.get("itemprop")
        cnt = meta.get("content")
        if prop and cnt and any(k in prop.lower() for k in ["date", "time", "publish", "created", "modified"]):
            meta_candidates[prop] = cnt

    # 2. Collect <time> elements
    time_candidates = []
    for t in soup.find_all("time"):
        time_candidates.append({
            "datetime": t.get("datetime"),
            "text": t.get_text(" ", strip=True),
        })

    # 3. Collect JSON-LD dates
    json_ld_candidates = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or s.get_text() or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    pub = item.get("datePublished") or item.get("dateCreated")
                    if pub:
                        json_ld_candidates.append({"type": item.get("@type"), "date": pub})
        except Exception:
            pass

    # Extract final authoritative result
    extracted_iso, method = extract_publication_time_with_method(soup)

    return {
        "url": url,
        "headline": headline,
        "meta_candidates": meta_candidates,
        "time_candidates": time_candidates,
        "json_ld_candidates": json_ld_candidates,
        "extracted_published_at": extracted_iso,
        "extraction_method": method,
    }


def run_diagnostics():
    print("=" * 80)
    print("LIVE MEDIA EXTRACTION DIAGNOSTIC RUN")
    print("=" * 80)

    fetcher = PageFetcher()
    et_scraper = ETBrandEquityScraper()
    e4m_scraper = Exchange4mediaScraper()

    # 1. ET BrandEquity Diagnostic
    print("\n--- ET BrandEquity Live Inspection ---")
    et_articles, _ = et_scraper.scrape_homepage(enrich=False)
    et_sample_urls = [a.url for a in et_articles[:4]] if et_articles else [
        "https://brandequity.economictimes.indiatimes.com/news/marketing/why-indias-pressure-test-drives-global-success/134425616"
    ]

    for url in et_sample_urls:
        res = inspect_article_page(url, fetcher)
        print(f"\nURL: {res.get('url')}")
        print(f"Headline: {res.get('headline')}")
        print(f"Meta Candidates: {json.dumps(res.get('meta_candidates', {}), indent=2)}")
        print(f"Time Tag Candidates: {json.dumps(res.get('time_candidates', []), indent=2)}")
        print(f"JSON-LD Candidates: {json.dumps(res.get('json_ld_candidates', []), indent=2)}")
        print(f"Authoritative published_at: {res.get('extracted_published_at')}")
        print(f"Extraction Source: {res.get('extraction_method')}")

    # 2. Exchange4media Diagnostic
    print("\n--- Exchange4media Live Inspection ---")
    e4m_articles, _ = e4m_scraper.scrape_homepage(enrich=False)
    e4m_sample_urls = [a.url for a in e4m_articles[:4]] if e4m_articles else []

    for url in e4m_sample_urls:
        res = inspect_article_page(url, fetcher)
        print(f"\nURL: {res.get('url')}")
        print(f"Headline: {res.get('headline')}")
        print(f"Meta Candidates: {json.dumps(res.get('meta_candidates', {}), indent=2)}")
        print(f"Time Tag Candidates: {json.dumps(res.get('time_candidates', []), indent=2)}")
        print(f"JSON-LD Candidates: {json.dumps(res.get('json_ld_candidates', []), indent=2)}")
        print(f"Authoritative published_at: {res.get('extracted_published_at')}")
        print(f"Extraction Source: {res.get('extraction_method')}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_diagnostics()
