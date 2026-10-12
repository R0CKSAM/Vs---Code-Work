"""
Unit Test Suite for Phase 4: Change Detection & Historical Article Tracking
Covers mandatory TEST 1 through TEST 8.

Run with:
    python -m unittest tests/test_change_detection.py
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database.connection import get_db
from database.schema import init_schema, init_db
from database.repository import Repository

try:
    from app.services.change_detector import ChangeDetector, compute_content_hash
except ImportError:
    from backend.app.services.change_detector import ChangeDetector, compute_content_hash


class TestChangeDetection(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for test isolation
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Initialize schema
        init_schema(self.db_path)
        self.repo = Repository(self.db_path)
        self.detector = ChangeDetector(self.db_path)

        # Seed initial websites
        self.et_site = self.repo.get_or_create_website(
            name="ET BrandEquity",
            key="et_brand_equity",
            base_url="https://brandequity.economictimes.indiatimes.com/",
        )
        self.e4m_site = self.repo.get_or_create_website(
            name="Exchange4media",
            key="exchange4media",
            base_url="https://www.exchange4media.com/",
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_01_first_run_empty_database_new_article(self):
        """
        TEST 1: Run 1 on empty database with article A.
        Expected: NEW = 1, UPDATED = 0, UNCHANGED = 0, REMOVED = 0.
        article_versions has 1 row with version_number = 1.
        """
        scraped_items = [
            {
                "url": "https://brandequity.economictimes.indiatimes.com/news/business-of-brands/story-a/101",
                "headline": "Story A: Groundbreaking Brand Launch",
                "summary": "Brand A launches innovative consumer initiative.",
                "image_url": "https://img.etb.com/101.jpg",
                "section": "Business of Brands",
                "published_at": "2026-09-23T10:00:00Z",
                "scraped_at": "2026-09-23T10:05:00Z",
            }
        ]

        result = self.detector.process_scrape_result(
            website_key="et_brand_equity",
            scraped_items=scraped_items,
            scrape_success=True,
            duration_ms=120,
        )

        self.assertEqual(result["new"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unchanged"], 0)
        self.assertEqual(result["removed"], 0)

        # Check database
        article = self.repo.get_article_by_url(self.et_site["id"], scraped_items[0]["url"])
        self.assertIsNotNone(article)
        self.assertEqual(article["status"], "ACTIVE")

        versions = self.repo.get_article_versions(article["id"])
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version_number"], 1)
        self.assertEqual(versions[0]["change_type"], "NEW")
        self.assertEqual(versions[0]["headline"], scraped_items[0]["headline"])
        self.assertIsNone(versions[0]["valid_to"])

    def test_02_second_run_same_article_unchanged(self):
        """
        TEST 2: Run 2 with same article A, same hash.
        Expected: NEW = 0, UPDATED = 0, UNCHANGED = 1, REMOVED = 0.
        article_versions STILL has 1 row. articles.last_seen_at is updated.
        """
        scraped_items = [
            {
                "url": "https://brandequity.economictimes.indiatimes.com/news/business-of-brands/story-a/101",
                "headline": "Story A: Groundbreaking Brand Launch",
                "summary": "Brand A launches innovative consumer initiative.",
                "image_url": "https://img.etb.com/101.jpg",
                "section": "Business of Brands",
                "published_at": "2026-09-23T10:00:00Z",
                "scraped_at": "2026-09-23T10:05:00Z",
            }
        ]

        # First run
        self.detector.process_scrape_result(
            website_key="et_brand_equity",
            scraped_items=scraped_items,
            scrape_success=True,
        )
        article_before = self.repo.get_article_by_url(self.et_site["id"], scraped_items[0]["url"])

        # Second run
        result2 = self.detector.process_scrape_result(
            website_key="et_brand_equity",
            scraped_items=scraped_items,
            scrape_success=True,
        )

        self.assertEqual(result2["new"], 0)
        self.assertEqual(result2["updated"], 0)
        self.assertEqual(result2["unchanged"], 1)
        self.assertEqual(result2["removed"], 0)

        # Versions count must still be 1
        versions = self.repo.get_article_versions(article_before["id"])
        self.assertEqual(len(versions), 1)

    def test_03_third_run_modified_headline_updated(self):
        """
        TEST 3: Run 3 with same URL, modified headline.
        Expected: NEW = 0, UPDATED = 1, UNCHANGED = 0, REMOVED = 0.
        article_versions has 2 rows:
          v1: valid_to is set (superseded)
          v2: valid_to is NULL (active)
        """
        url = "https://brandequity.economictimes.indiatimes.com/news/business-of-brands/story-a/101"
        item_v1 = [
            {
                "url": url,
                "headline": "Story A: Groundbreaking Brand Launch",
                "summary": "Brand A launches innovative consumer initiative.",
                "image_url": "https://img.etb.com/101.jpg",
                "section": "Business of Brands",
                "published_at": "2026-09-23T10:00:00Z",
            }
        ]
        self.detector.process_scrape_result("et_brand_equity", item_v1, scrape_success=True)

        item_v2 = [
            {
                "url": url,
                "headline": "Story A: REVISED Groundbreaking Brand Launch Expands Nationwide",
                "summary": "Brand A launches innovative consumer initiative.",
                "image_url": "https://img.etb.com/101.jpg",
                "section": "Business of Brands",
                "published_at": "2026-09-23T10:00:00Z",
            }
        ]
        result = self.detector.process_scrape_result("et_brand_equity", item_v2, scrape_success=True)

        self.assertEqual(result["new"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["unchanged"], 0)
        self.assertEqual(result["removed"], 0)

        article = self.repo.get_article_by_url(self.et_site["id"], url)
        versions = self.repo.get_article_versions(article["id"])
        self.assertEqual(len(versions), 2)

        # v1 must be superseded
        v1 = [v for v in versions if v["version_number"] == 1][0]
        self.assertIsNotNone(v1["valid_to"])
        self.assertEqual(v1["headline"], item_v1[0]["headline"])

        # v2 must be current active
        v2 = [v for v in versions if v["version_number"] == 2][0]
        self.assertIsNone(v2["valid_to"])
        self.assertEqual(v2["headline"], item_v2[0]["headline"])
        self.assertEqual(v2["change_type"], "UPDATED")

    def test_04_timestamp_only_change_is_unchanged(self):
        """
        TEST 4: Scraped article with different scraped_at timestamp only.
        Expected: content hash does NOT change, classified as UNCHANGED.
        """
        url = "https://brandequity.economictimes.indiatimes.com/news/digital/story-timestamp/202"
        item_run1 = [
            {
                "url": url,
                "headline": "Digital Trends in Programmatic Advertising",
                "summary": "Analysis of modern ad exchanges.",
                "image_url": "https://img.etb.com/202.jpg",
                "section": "Digital",
                "published_at": "2026-09-23T08:00:00Z",
                "scraped_at": "2026-09-23T08:05:00Z",
            }
        ]
        self.detector.process_scrape_result("et_brand_equity", item_run1, scrape_success=True)

        item_run2 = [
            {
                "url": url,
                "headline": "Digital Trends in Programmatic Advertising",
                "summary": "Analysis of modern ad exchanges.",
                "image_url": "https://img.etb.com/202.jpg",
                "section": "Digital",
                "published_at": "2026-09-23T08:00:00Z",
                "scraped_at": "2026-09-23T11:45:00Z",  # Different scraped_at!
            }
        ]
        result = self.detector.process_scrape_result("et_brand_equity", item_run2, scrape_success=True)

        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(result["updated"], 0)

        # Hash check
        hash1 = compute_content_hash(item_run1[0]["headline"], item_run1[0]["summary"], item_run1[0]["image_url"], item_run1[0]["section"], item_run1[0]["published_at"])
        hash2 = compute_content_hash(item_run2[0]["headline"], item_run2[0]["summary"], item_run2[0]["image_url"], item_run2[0]["section"], item_run2[0]["published_at"])
        self.assertEqual(hash1, hash2)

    def test_05_article_disappears_from_valid_scrape_marked_removed(self):
        """
        TEST 5: Article disappears from a valid scrape that returned 5+ articles.
        Expected: REMOVED = 1, articles.status = 'REMOVED', removed_at timestamp set.
        """
        # Baseline with 6 articles
        articles_run1 = [
            {
                "url": f"https://www.exchange4media.com/media-tv/story-{i}-300",
                "headline": f"Broadcast Story #{i}",
                "summary": f"Summary for story {i}",
                "section": "Media TV",
                "published_at": "2026-09-23T09:00:00Z",
            }
            for i in range(1, 7)
        ]
        self.detector.process_scrape_result("exchange4media", articles_run1, scrape_success=True)

        target_article = self.repo.get_article_by_url(self.e4m_site["id"], articles_run1[0]["url"])
        self.assertEqual(target_article["status"], "ACTIVE")

        # Run 2: Articles 2 through 6 return (5 articles, >= MIN_ARTICLES_FOR_SAFE_REMOVAL), but Article 1 is omitted
        articles_run2 = articles_run1[1:]
        self.assertEqual(len(articles_run2), 5)

        result = self.detector.process_scrape_result("exchange4media", articles_run2, scrape_success=True)
        self.assertEqual(result["removed"], 1)

        # Verify article 1 status is REMOVED
        removed_art = self.repo.get_article_by_url(self.e4m_site["id"], articles_run1[0]["url"])
        self.assertEqual(removed_art["status"], "REMOVED")
        self.assertIsNotNone(removed_art["removed_at"])

    def test_06_scraper_failure_zero_articles_prevents_false_removal(self):
        """
        TEST 6: Scraper fails or returns 0 articles (below safety threshold 5).
        Expected: REMOVED = 0. All articles remain ACTIVE. False removal prevented.
        """
        articles = [
            {
                "url": f"https://brandequity.economictimes.indiatimes.com/news/marketing/story-{i}",
                "headline": f"Marketing Campaign #{i}",
                "summary": f"Summary for marketing {i}",
                "section": "Marketing",
                "published_at": "2026-09-23T09:00:00Z",
            }
            for i in range(1, 10)
        ]
        self.detector.process_scrape_result("et_brand_equity", articles, scrape_success=True)

        # Scrape fails: scrape_success=False and scraped_items=[]
        fail_result = self.detector.process_scrape_result(
            "et_brand_equity",
            scraped_items=[],
            scrape_success=False,
            error_message="HTTP 503 Service Unavailable",
        )

        self.assertEqual(fail_result["removed"], 0)

        # All 9 articles must still be ACTIVE
        all_articles = self.repo.get_active_articles_by_website(self.et_site["id"])
        self.assertEqual(len(all_articles), 9)
        for a in all_articles:
            self.assertEqual(a["status"], "ACTIVE")
            self.assertIsNone(a["removed_at"])

    def test_07_cross_publisher_independence(self):
        """
        TEST 7: Similar headlines across ET and E4M with distinct URLs.
        Expected: Stored as 2 separate articles, independently tracked.
        """
        et_item = [
            {
                "url": "https://brandequity.economictimes.indiatimes.com/news/industry/merger-2026",
                "headline": "Media Giant Announces Mega Merger in 2026",
                "summary": "ET BrandEquity coverage of media conglomerate consolidation.",
                "section": "Industry",
                "published_at": "2026-09-23T11:00:00Z",
            }
        ]
        e4m_item = [
            {
                "url": "https://www.exchange4media.com/industry-briefing/merger-2026",
                "headline": "Media Giant Announces Mega Merger in 2026",
                "summary": "Exchange4media coverage of media conglomerate consolidation.",
                "section": "Industry Briefing",
                "published_at": "2026-09-23T11:00:00Z",
            }
        ]

        self.detector.process_scrape_result("et_brand_equity", et_item, scrape_success=True)
        self.detector.process_scrape_result("exchange4media", e4m_item, scrape_success=True)

        et_art = self.repo.get_article_by_url(self.et_site["id"], et_item[0]["url"])
        e4m_art = self.repo.get_article_by_url(self.e4m_site["id"], e4m_item[0]["url"])

        self.assertIsNotNone(et_art)
        self.assertIsNotNone(e4m_art)
        self.assertNotEqual(et_art["id"], e4m_art["id"])
        self.assertEqual(et_art["website_id"], self.et_site["id"])
        self.assertEqual(e4m_art["website_id"], self.e4m_site["id"])

    def test_08_composite_unique_key_different_website_same_url(self):
        """
        TEST 8: Same URL under different website_id.
        Expected: Stored as 2 distinct database rows thanks to UNIQUE(website_id, url).
        """
        shared_url = "https://syndicated-newswire.com/article/press-release-101"
        item_et = [
            {
                "url": shared_url,
                "headline": "Newswire Release on BrandEquity",
                "summary": "Syndicated piece.",
                "section": "News",
            }
        ]
        item_e4m = [
            {
                "url": shared_url,
                "headline": "Newswire Release on Exchange4media",
                "summary": "Syndicated piece.",
                "section": "News",
            }
        ]

        self.detector.process_scrape_result("et_brand_equity", item_et, scrape_success=True)
        self.detector.process_scrape_result("exchange4media", item_e4m, scrape_success=True)

        et_art = self.repo.get_article_by_url(self.et_site["id"], shared_url)
        e4m_art = self.repo.get_article_by_url(self.e4m_site["id"], shared_url)

        self.assertIsNotNone(et_art)
        self.assertIsNotNone(e4m_art)
        self.assertNotEqual(et_art["id"], e4m_art["id"])


if __name__ == "__main__":
    unittest.main()
