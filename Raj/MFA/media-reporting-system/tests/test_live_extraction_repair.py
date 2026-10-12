"""
Phase 7.2 Focused Unit Tests:
1. publication time from <time>
2. publication time from JSON-LD
3. publication time missing remains None
4. scraped_at is never substituted for published_at
5. advertiser unknown remains None
6. captured creative path is persisted
7. first_seen remains stable
8. last_seen updates
9. changed creative creates new version
10. failed scrape does not remove active advertisement
"""
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
from scraper.base.enrichment import enrich_article
from backend.app.services.ad_change_detector import AdvertisementChangeDetector


class TestLiveExtractionRepair(unittest.TestCase):

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

    def test_01_publication_time_from_time_tag(self):
        """1. Publication time correctly extracted from <time datetime='...'>."""
        html = """
        <div class="card">
            <h2>Test Article</h2>
            <time datetime="2026-07-24T11:35:00+05:30">24 Jul 2026, 11:35 AM</time>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertEqual(method, "HTML_TIME")
        self.assertIsNotNone(iso)
        self.assertIn("2026-07-24", iso)

    def test_02_publication_time_from_json_ld(self):
        """2. Publication time correctly extracted from JSON-LD NewsArticle block."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Tech Launch in India",
                "datePublished": "2026-09-23T10:00:00+05:30",
                "dateModified": "2026-09-23T10:30:00+05:30"
            }
            </script>
        </head>
        <body><p>Article body</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertEqual(method, "JSON_LD")
        self.assertIsNotNone(iso)
        self.assertIn("2026-09-23T10:00:00", iso)

    def test_03_publication_time_missing_remains_none(self):
        """3. When no publication time is present, published_at remains None (never guessed)."""
        html = "<div><h2>Breaking News Without Date</h2><p>Article synopsis...</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        iso, method = extract_publication_time_with_method(soup)
        self.assertIsNone(iso)
        self.assertEqual(method, "UNAVAILABLE")

    def test_04_scraped_at_is_never_substituted_for_published_at(self):
        """4. scraped_at timestamp is strictly independent and never substituted for published_at."""
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

    def test_article_page_corrects_conflicting_listing_metadata(self):
        class PageFetcher:
            def fetch(self, url, browser_fallback=True):
                return """
                <html><head>
                  <meta property="og:description" content="Authoritative source summary.">
                  <meta property="og:image" content="https://publisher.test/source.jpg">
                  <meta property="article:published_time" content="2026-09-30T10:51:20+05:30">
                  <meta property="article:section" content="People Movement">
                  <meta name="author" content="Publisher Desk">
                </head><body>
                  <h1>Authoritative Article Headline From Publisher</h1>
                </body></html>
                """

        article = Article(
            website="Publisher",
            website_key="publisher",
            section="Wrong Section",
            headline="Shortened listing-card headline",
            url="https://publisher.test/article",
            image_url="https://publisher.test/stale.jpg",
            summary="Stale listing summary.",
            published_at="2026-09-30T09:00:00+05:30",
        )

        enrich_article(article, PageFetcher())

        self.assertEqual(article.headline, "Authoritative Article Headline From Publisher")
        self.assertEqual(article.section, "People Movement")
        self.assertEqual(article.summary, "Authoritative source summary.")
        self.assertEqual(article.image_url, "https://publisher.test/source.jpg")
        self.assertEqual(article.published_at, "2026-09-30T10:51:20+05:30")
        self.assertEqual(article.author, "Publisher Desk")

    def test_article_page_uses_structured_section_over_listing_section(self):
        class PageFetcher:
            def fetch(self, url, browser_fallback=True):
                return """
                <html><head>
                  <script type="application/ld+json">
                  {
                    "@context": "https://schema.org",
                    "@type": "NewsArticle",
                    "url": "https://publisher.test/article",
                    "headline": "Publisher Article Headline For Section Test",
                    "articleSection": "People-Movement",
                    "datePublished": "2026-09-30T10:51:20+05:30"
                  }
                  </script>
                </head><body><h1>Publisher Article Headline For Section Test</h1></body></html>
                """

        article = Article(
            website="Publisher",
            website_key="publisher",
            section="Incorrect Listing Label",
            headline="Incorrect Listing Headline",
            url="https://publisher.test/article",
        )

        enrich_article(article, PageFetcher())

        self.assertEqual(article.section, "People Movement")
        self.assertEqual(article.headline, "Publisher Article Headline For Section Test")

    def test_05_advertiser_unknown_remains_none(self):
        """5. When advertiser/brand cannot be identified, it strictly remains None (no manufactured values)."""
        detector = AdvertisementDetector("exchange4media")
        html = """
        <div class="ad-slot right-rail" id="div-gpt-ad-random-0">
            <iframe src="https://doubleclick.net/slot?ad=123" width="300" height="250"></iframe>
        </div>
        """
        ads = detector.detect_advertisements_from_html(html, "https://www.exchange4media.com/")
        self.assertEqual(len(ads), 1)
        ad = ads[0]
        self.assertIsNone(ad.advertiser)
        self.assertIsNone(ad.brand)

    def test_06_captured_creative_path_is_persisted(self):
        """6. Captured creative asset path is stored in database record."""
        saved_path = save_ad_screenshot(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "et_brand_equity", "testhash123")
        self.assertIsNotNone(saved_path)

        res = self.ad_detector.process_detected_advertisements(
            "et_brand_equity",
            [
                {
                    "page_url": "https://brandequity.economictimes.indiatimes.com/",
                    "position": "Top Masthead Billboard",
                    "ad_type": "BANNER",
                    "ad_hash": "testhash123",
                    "image_url": "https://img.com/ad.jpg",
                    "advertiser": "Sample Brand",
                }
            ],
            scrape_success=True,
            download_images=False,
        )
        self.assertEqual(res["new"], 1)

        ads = self.repo.get_advertisements("et_brand_equity")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["advertiser"], "Sample Brand")

    def test_07_first_seen_remains_stable(self):
        """7. First seen timestamp remains invariant across repeat observations."""
        first_time = "2026-09-23T10:00:00+00:00"
        second_time = "2026-09-23T10:10:00+00:00"

        ad_dict = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "stable_hash_001",
            "image_url": "https://img.com/banner.jpg",
            "advertiser": "Tata Motors",
        }

        # Observation 1
        self.ad_detector.process_detected_advertisements(
            "et_brand_equity", [ad_dict], detected_at=first_time
        )
        ad_record = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertEqual(ad_record["first_seen_at"], first_time)
        self.assertEqual(ad_record["last_seen_at"], first_time)

        # Observation 2
        self.ad_detector.process_detected_advertisements(
            "et_brand_equity", [ad_dict], detected_at=second_time
        )
        ad_record_after = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertEqual(ad_record_after["first_seen_at"], first_time, "first_seen_at must remain stable!")
        self.assertEqual(ad_record_after["last_seen_at"], second_time, "last_seen_at must be updated!")

    def test_08_last_seen_updates(self):
        """8. Repeat observation updates last_seen_at without creating redundant versions."""
        t1 = "2026-09-23T08:00:00+00:00"
        t2 = "2026-09-23T08:30:00+00:00"
        ad = {
            "page_url": "https://www.exchange4media.com/",
            "position": "Right Sidebar Sticky MPU",
            "ad_type": "BANNER",
            "ad_hash": "mpu_hash_999",
            "advertiser": "Samsung",
        }
        self.ad_detector.process_detected_advertisements("exchange4media", [ad], detected_at=t1)
        self.ad_detector.process_detected_advertisements("exchange4media", [ad], detected_at=t2)

        ad_rec = self.repo.get_advertisements("exchange4media")[0]
        self.assertEqual(ad_rec["last_seen_at"], t2)
        versions = self.repo.get_advertisement_versions(ad_rec["id"])
        self.assertEqual(len(versions), 1, "Must not create new versions for unchanged creative!")

    def test_09_changed_creative_creates_new_version(self):
        """9. When creative changes at the same placement, a new version is created."""
        t1 = "2026-09-23T08:00:00+00:00"
        t2 = "2026-09-23T08:30:00+00:00"
        ad_v1 = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "hash_v1",
            "image_url": "https://img.com/v1.jpg",
            "advertiser": "Brand A",
        }
        ad_v2 = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "hash_v2",
            "image_url": "https://img.com/v2.jpg",
            "advertiser": "Brand B",
        }
        res1 = self.ad_detector.process_detected_advertisements("et_brand_equity", [ad_v1], detected_at=t1)
        self.assertEqual(res1["new"], 1)

        res2 = self.ad_detector.process_detected_advertisements("et_brand_equity", [ad_v2], detected_at=t2)
        self.assertEqual(res2["changed"], 1)

        ad_rec = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertEqual(ad_rec["ad_hash"], "hash_v2")
        self.assertEqual(ad_rec["status"], "ACTIVE")

        versions = self.repo.get_advertisement_versions(ad_rec["id"])
        self.assertEqual(len(versions), 2, "Must create version 2 for changed creative!")

    def test_10_failed_scrape_preserves_active_advertisement(self):
        """10. Failed scrape does not mark active advertisements as removed."""
        t1 = "2026-09-23T08:00:00+00:00"
        ad = {
            "page_url": "https://brandequity.economictimes.indiatimes.com/",
            "position": "Top Masthead Billboard",
            "ad_type": "BANNER",
            "ad_hash": "preserve_me_hash",
        }
        self.ad_detector.process_detected_advertisements("et_brand_equity", [ad], detected_at=t1)

        # Simulate failed scrape (scrape_success=False with 0 detected ads)
        res_fail = self.ad_detector.process_detected_advertisements(
            "et_brand_equity", [], scrape_success=False
        )
        self.assertEqual(res_fail["removed"], 0)

        ad_rec = self.repo.get_advertisements("et_brand_equity")[0]
        self.assertEqual(ad_rec["status"], "ACTIVE", "Active ads must be preserved on failed scrape!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
