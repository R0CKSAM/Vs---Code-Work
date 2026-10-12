"""
Media Reporting System - Phase 6 Live Advertisement Diagnostic Tool
Tests live advertisement detection on ET BrandEquity and Exchange4media,
persists detected placements through the database repository, and reports telemetry.
"""
import sys
import os
from pathlib import Path

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database.schema import init_db
from database.repository import db_repo
from scraper.advertisements import AdvertisementDetector
from scraper.base.fetcher import PageFetcher
try:
    from app.services.ad_change_detector import ad_change_detector
except ImportError:
    from backend.app.services.ad_change_detector import ad_change_detector



TARGET_SITES = [
    {
        "key": "et_brand_equity",
        "name": "ET BrandEquity",
        "url": "https://brandequity.economictimes.indiatimes.com/",
    },
    {
        "key": "exchange4media",
        "name": "Exchange4media",
        "url": "https://www.exchange4media.com/",
    },
]


def run_ad_diagnostics():
    print("=" * 70)
    print("  PHASE 6: ADVERTISEMENT MONITORING & DETECTION DIAGNOSTIC")
    print("=" * 70)

    # 1. Initialize schema
    print("\n[1/3] Initializing Advertisement Database Schema...")
    init_db()
    print("      --> Schema verified successfully.")

    fetcher = PageFetcher()

    # 2. Test ET BrandEquity & Exchange4media live detection
    for site in TARGET_SITES:
        key = site["key"]
        name = site["name"]
        url = site["url"]

        print(f"\n[2/3] Probing {name} ({url})...")
        try:
            html = fetcher.fetch(url)
            if not html:
                print(f"      [!] Failed to fetch HTML for {name}")
                continue

            detector = AdvertisementDetector(website_key=key)
            detected = detector.detect_advertisements_from_html(html, page_url=url)

            print(f"      --> Detected: {len(detected)} advertisement placement(s)")
            if detected:
                for idx, ad in enumerate(detected, 1):
                    brand = ad.brand or ad.advertiser or "Brand Unspecified"
                    print(f"          [{idx}] Type: {ad.ad_type} | Position: {ad.position}")
                    print(f"              Brand/Advertiser: {brand}")
                    if ad.campaign:
                        print(f"              Campaign: {ad.campaign}")
                    if ad.image_url:
                        print(f"              Image URL: {ad.image_url[:70]}...")
                    if ad.target_url:
                        print(f"              Target URL: {ad.target_url[:70]}...")
                    print(f"              Ad Hash: {ad.ad_hash[:16]}...")
            else:
                print("      --> No reliably detectable advertisements found on live static HTML (dynamic JS slots).")

            # Persist through ad change detector
            res = ad_change_detector.process_detected_advertisements(
                website_key=key,
                detected_ads=detected,
                scrape_success=True,
                download_images=False,
            )
            print(f"      --> Database State: new={res['new']} changed={res['changed']} unchanged={res['unchanged']} active_total={res['detected_count']}")

        except Exception as exc:
            print(f"      [!] Error probing {name}: {exc}")

    # 3. Report overall KPI metrics
    print("\n[3/3] Overall Advertisement Intelligence KPIs in Database:")
    kpis = db_repo.get_advertisement_kpis()
    print(f"      - Total Tracked Ads:   {kpis['total_ads']}")
    print(f"      - Active Live Ads:     {kpis['active_ads']}")
    print(f"      - Changed Creatives:   {kpis['changed_ads']}")
    print(f"      - Removed Ads:         {kpis['removed_ads']}")
    print(f"      - Unique Advertisers:  {kpis['unique_advertisers']}")
    print(f"      - Unique Brands:       {kpis['unique_brands']}")

    print("\n" + "=" * 70)
    print("  PHASE 6 ADVERTISEMENT MONITORING DIAGNOSTICS COMPLETED!")
    print("=" * 70)


if __name__ == "__main__":
    run_ad_diagnostics()
