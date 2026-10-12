"""
Phase 7.3 Focused Unit & Verification Tests:
1. ET article with real publication timestamp -> published_at populated.
2. E4M article with real publication timestamp -> published_at populated.
3. scraped_at never used as published_at.
4. relative "1 hour ago" is not treated as authoritative timestamp unless an actual source timestamp exists.
5. srcset/data-src image extraction.
6. actual creative URL persisted.
7. creative download content type validated.
8. advertiser remains None when unsupported.
9. first_seen remains invariant.
10. last_seen updates.
11. creative change creates a new version.
12. dashboard KPI equals actual database count.
13. dashboard table count equals API result after filters.
14. removed ads do not appear under Active filter.
15. advertisement detail exposes first_seen and last_seen.
16. no editorial hero image is treated as advertisement.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bs4 import BeautifulSoup
from database.schema import init_db
from database.repository import Repository
from scraper.base.article import Article
from scraper.advertisements import AdvertisementDetector, DetectedAdvertisement
from scraper.ad_image_storage import save_ad_screenshot
from scraper.utils.date_parser import (
    parse_date_to_iso,
    extract_publication_time_with_method,
)
from backend.app.services.ad_change_detector import AdvertisementChangeDetector


class TestPhase73LiveRepair(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()

        init_db(self.db_path)
        self.repo = Repository(self.db_path)
        self.ad_detector = AdvertisementChangeDetector(self.repo)

    def tearDown(self):
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_01_et_live_article_published_at_populated(self):
        """1. ET live article with publish-date/created-date metadata extracts published_at."""
        html = """
        <html>
        <head>
            <meta name="publish-date" content="Wed, 23 Sep 2026 10:03:22 +0530" />
            <meta name="created-date" content="Wed, 23 Sep 2026 10:03:22 +0530" />
            <meta property="og:updated_time" content="2026-09-23 10:03:22" />
        </head>
        <body><h1>Why India's Pressure Test Drives Global Success</h1></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertEqual(method, "META")
        self.assertIsNotNone(iso)
        self.assertIn("2026-09-23", iso)

    def test_02_e4m_live_article_published_at_populated(self):
        """2. E4M live article with NewsArticle datePublished extracts published_at."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Ad Spending Growth in Q3",
                "datePublished": "2026-09-23T14:30:00+05:30"
            }
            </script>
        </head>
        <body><h1>Ad Spending Growth in Q3</h1></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertEqual(method, "JSON_LD")
        self.assertIsNotNone(iso)
        self.assertIn("2026-09-23T14:30:00", iso)

    def test_03_scraped_at_never_used_as_published_at(self):
        """3. scraped_at timestamp is strictly independent and never substituted for published_at."""
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Marketing",
            headline="Sample Article Headline",
            url="https://brandequity.economictimes.indiatimes.com/news/123",
            published_at=None,
        )
        art.finalize()
        self.assertIsNone(art.published_at)
        self.assertTrue(bool(art.scraped_at))
        self.assertNotEqual(art.published_at, art.scraped_at)

    def test_04_relative_time_not_authoritative_unless_source_exists(self):
        """4. Relative string without authoritative timestamp returns None."""
        html = "<div><h2>Breaking News Without Date</h2><p>1 hour ago</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertIsNone(iso)
        self.assertEqual(method, "UNAVAILABLE")

    def test_05_srcset_and_data_src_image_extraction(self):
        """5. Ad container extracts lazy-loaded data-src or srcset image."""
        detector = AdvertisementDetector("et_brand_equity")
        html = """
        <div class="ad-slot top-banner" id="div-gpt-ad-12345">
            <img data-src="https://img.etb2bimg.com/ads/banner_masthead_2026.jpg" alt="L'Oreal India Campaign" />
        </div>
        """
        ads = detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0].image_url, "https://img.etb2bimg.com/ads/banner_masthead_2026.jpg")

    def test_06_actual_creative_url_persisted(self):
        """6. Resolved creative URL is stored in database record."""
        res = self.ad_detector.process_detected_advertisements(
            "et_brand_equity",
            [
                {
                    "page_url": "https://brandequity.economictimes.indiatimes.com/",
                    "position": "Top Masthead Billboard",
                    "ad_type": "BANNER",
                    "ad_hash": "hash_creative_url_test",
                    "image_url": "https://img.etb2bimg.com/ads/real_creative.jpg",
                    "target_url": "https://brand.com/campaign",
                    "advertiser": "L'Oreal",
                }
            ],
            download_images=False,
        )
        self.assertEqual(res["new"], 1)
        ads = self.repo.get_advertisements("et_brand_equity")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["image_url"], "https://img.etb2bimg.com/ads/real_creative.jpg")
        self.assertEqual(ads[0]["target_url"], "https://brand.com/campaign")

    def test_07_creative_download_content_type_validated(self):
        """7. save_ad_screenshot accepts valid image bytes and persists file."""
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        saved_path = save_ad_screenshot(fake_png, "et_brand_equity", "hash_png_test")
        self.assertIsNotNone(saved_path)
        self.assertTrue(saved_path.endswith(".png"))

    def test_08_advertiser_unknown_remains_none(self):
        """8. Unknown advertiser/brand metadata strictly remains None."""
        detector = AdvertisementDetector("exchange4media")
        html = """
        <div class="ad-slot right-rail" id="div-gpt-ad-slot-mpu">
            <iframe src="https://doubleclick.net/slot?ad=999" width="300" height="250"></iframe>
        </div>
        """
        ads = detector.detect_advertisements_from_html(html, "https://www.exchange4media.com/")
        self.assertEqual(len(ads), 1)
        self.assertIsNone(ads[0].advertiser)
        self.assertIsNone(ads[0].brand)

    def test_09_first_seen_remains_invariant(self):
        """9. first_seen_at timestamp remains invariant across recurring scrapes."""
        t1 = "2026-09-23T10:00:00+00:00"
        t2 = "2026-09-23T10:30:00+00:00"
        ad_data = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "invariant_hash_01",
            "advertiser": "Tata",
        }
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad_data], detected_at=t1)
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad_data], detected_at=t2)

        ad = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertEqual(ad["first_seen_at"], t1)
        self.assertEqual(ad["last_seen_at"], t2)

    def test_10_last_seen_updates(self):
        """10. Repeat scrape updates last_seen_at without creating duplicate rows."""
        t1 = "2026-09-23T08:00:00+00:00"
        t2 = "2026-09-23T08:20:00+00:00"
        ad_data = {
            "page_url": "https://www.exchange4media.com/",
            "position": "Right Sidebar Sticky MPU",
            "ad_type": "BANNER",
            "ad_hash": "last_seen_hash_02",
        }
        self.ad_detector.process_detected_advertisements("exchange4media", [ad_data], detected_at=t1)
        self.ad_detector.process_detected_advertisements("exchange4media", [ad_data], detected_at=t2)

        ads = self.repo.get_advertisements("exchange4media")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["last_seen_at"], t2)

    def test_11_creative_change_creates_new_version(self):
        """11. Changed creative at the same slot creates version 2."""
        t1 = "2026-09-23T08:00:00+00:00"
        t2 = "2026-09-23T08:30:00+00:00"
        v1 = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "creative_v1",
            "advertiser": "Brand A",
        }
        v2 = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "creative_v2",
            "advertiser": "Brand B",
        }
        self.ad_detector.process_detected_advertisements("et_brand_equity", [v1], detected_at=t1)
        res = self.ad_detector.process_detected_advertisements("et_brand_equity", [v2], detected_at=t2)
        self.assertEqual(res["changed"], 1)

        ad = self.repo.get_advertisements("et_brand_equity")[0]
        versions = self.repo.get_advertisement_versions(ad["id"])
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[1]["version_number"], 2)

    def test_12_dashboard_kpi_equals_database_count(self):
        """12. Dashboard KPI total_ads equals actual database count."""
        ad1 = {"page_url": "https://brandequity.economictimes.indiatimes.com/", "position": "Top Masthead Billboard", "ad_type": "BANNER", "ad_hash": "kpi_1"}
        ad2 = {"page_url": "https://brandequity.economictimes.indiatimes.com/", "position": "Right Sidebar Sticky MPU", "ad_type": "BANNER", "ad_hash": "kpi_2"}
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad1, ad2])

        kpis = self.repo.get_advertisement_kpis("et_brand_equity")
        self.assertEqual(kpis["total_ads"], 2)
        self.assertEqual(kpis["active_ads"], 2)

    def test_13_dashboard_table_count_equals_api_result(self):
        """13. Filtered database queries return exact record counts."""
        ad1 = {"page_url": "https://brandequity.economictimes.indiatimes.com/", "position": "Top Masthead Billboard", "ad_type": "BANNER", "ad_hash": "t1"}
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad1])

        ads = self.repo.get_advertisements(website_key="et_brand_equity", status="ACTIVE")
        self.assertEqual(len(ads), 1)

    def test_14_removed_ads_do_not_appear_under_active_filter(self):
        """14. Inactive/removed ads are excluded when filtering status='ACTIVE'."""
        ad1 = {"page_url": "https://brandequity.economictimes.indiatimes.com/", "position": "Top Masthead Billboard", "ad_type": "BANNER", "ad_hash": "rem_1"}
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad1])
        # Scrape with 0 ads -> marks active ads as removed
        self.ad_detector.process_detected_advertisements("et_brand_equity", [], scrape_success=True)

        active_ads = self.repo.get_advertisements("et_brand_equity", status="ACTIVE")
        self.assertEqual(len(active_ads), 0)

        all_ads = self.repo.get_advertisements("et_brand_equity", status="ALL")
        self.assertEqual(len(all_ads), 1)
        self.assertEqual(all_ads[0]["status"], "REMOVED")

    def test_15_advertisement_detail_exposes_first_and_last_seen(self):
        """15. Advertisement detail record contains both first_seen_at and last_seen_at."""
        ad1 = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "detail_hash_01",
        }
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad1], detected_at="2026-09-23T11:00:00+00:00")
        ad_rec = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertIn("first_seen_at", ad_rec)
        self.assertIn("last_seen_at", ad_rec)
        self.assertEqual(ad_rec["first_seen_at"], "2026-09-23T11:00:00+00:00")

    def test_16_no_editorial_hero_image_treated_as_advertisement(self):
        """16. Editorial news hero images, logos, and nav elements are never classified as ads."""
        detector = AdvertisementDetector("et_brand_equity")
        html = """
        <header><div class="logo"><img src="https://img.com/site_logo.svg" alt="ETBrandEquity Logo"></div></header>
        <article class="news-card">
            <figure class="hero-image"><img src="https://img.com/story_hero.jpg" alt="Story Hero"></figure>
            <h2>Breaking Marketing Story</h2>
        </article>
        """
        ads = detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 0, "Editorial hero images and logos must never be detected as ads!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
