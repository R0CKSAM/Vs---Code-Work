"""
Phase 6 - Advertisement Database Persistence & Change Detection Tests
Tests ad lifecycle tracking (NEW, UNCHANGED, CHANGED, REMOVED), creative versioning,
failed scrape safeguards, and publisher isolation using an isolated SQLite database.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database.schema import init_db
from database.repository import Repository
try:
    from app.services.ad_change_detector import AdvertisementChangeDetector
except ImportError:
    from backend.app.services.ad_change_detector import AdvertisementChangeDetector
from scraper.advertisements import DetectedAdvertisement



class TestAdDatabasePersistence(unittest.TestCase):

    def setUp(self):
        # Create isolated temporary SQLite database for each test
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()

        init_db(self.db_path)
        self.repo = Repository(self.db_path)
        self.change_detector = AdvertisementChangeDetector(self.repo)

        # Initialize websites
        self.repo.get_or_create_website("ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/")
        self.repo.get_or_create_website("Exchange4media", "exchange4media", "https://www.exchange4media.com/")

    def tearDown(self):
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_01_first_ad_detection_creates_advertisement_and_v1(self):
        """1. First detection of an ad creates an advertisement record and version 1."""
        ad = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            advertiser="Samsung",
            brand="Samsung Galaxy",
            campaign="Galaxy Unpacked 2026",
            image_url="https://images.samsung.com/banner-970x250.jpg",
            target_url="https://samsung.com/galaxy",
        )
        res = self.change_detector.process_detected_advertisements(
            website_key="et_brand_equity",
            detected_ads=[ad],
            download_images=False,
            detected_at="2026-09-23T10:00:00+00:00",
        )
        self.assertEqual(res["new"], 1)
        self.assertEqual(res["changed"], 0)

        ads = self.repo.get_advertisements(website_key="et_brand_equity")
        self.assertEqual(len(ads), 1)
        db_ad = ads[0]
        self.assertEqual(db_ad["advertiser"], "Samsung")
        self.assertEqual(db_ad["status"], "ACTIVE")
        self.assertEqual(db_ad["first_seen_at"], "2026-09-23T10:00:00+00:00")
        self.assertEqual(db_ad["last_seen_at"], "2026-09-23T10:00:00+00:00")

        versions = self.repo.get_advertisement_versions(db_ad["id"])
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version_number"], 1)
        self.assertEqual(versions[0]["change_type"], "NEW")

    def test_02_same_ad_detected_again_updates_last_seen_preserves_first_seen(self):
        """2. Same ad seen again preserves first_seen_at and updates last_seen_at without duplicate versions."""
        ad = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            advertiser="Samsung",
            brand="Samsung Galaxy",
            image_url="https://images.samsung.com/banner.jpg",
        )
        # Cycle 1
        self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad], download_images=False, detected_at="2026-09-23T10:00:00+00:00"
        )
        # Cycle 2 (10 minutes later)
        res2 = self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad], download_images=False, detected_at="2026-09-23T10:10:00+00:00"
        )
        self.assertEqual(res2["unchanged"], 1)
        self.assertEqual(res2["new"], 0)

        ads = self.repo.get_advertisements(website_key="et_brand_equity")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["first_seen_at"], "2026-09-23T10:00:00+00:00")
        self.assertEqual(ads[0]["last_seen_at"], "2026-09-23T10:10:00+00:00")

        versions = self.repo.get_advertisement_versions(ads[0]["id"])
        self.assertEqual(len(versions), 1, "Unchanged ad should not create a new version record")

    def test_03_changed_creative_creates_v2(self):
        """3. Changed creative at the same placement creates a new version record."""
        ad_v1 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            brand="Tata Motors",
            campaign="Curvv EV Launch",
            image_url="https://media.tatamotors.com/curvv_v1.jpg",
        )
        self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad_v1], download_images=False, detected_at="2026-09-23T10:00:00+00:00"
        )

        ad_v2 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            brand="Tata Motors",
            campaign="Curvv EV Festive Offer",
            image_url="https://media.tatamotors.com/curvv_v2_festive.jpg",
        )
        res2 = self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad_v2], download_images=False, detected_at="2026-09-23T10:20:00+00:00"
        )
        self.assertEqual(res2["changed"], 1)

        ads = self.repo.get_advertisements(website_key="et_brand_equity")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["campaign"], "Curvv EV Festive Offer")

        versions = self.repo.get_advertisement_versions(ads[0]["id"])
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["version_number"], 1)
        self.assertEqual(versions[0]["change_type"], "NEW")
        self.assertEqual(versions[1]["version_number"], 2)
        self.assertEqual(versions[1]["change_type"], "CHANGED")
        self.assertEqual(versions[1]["campaign"], "Curvv EV Festive Offer")

    def test_04_ad_disappears_from_successful_scrape_marked_removed(self):
        """4. When an ad is absent from a valid scrape run, it is marked REMOVED."""
        ad1 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            brand="Brand A",
        )
        ad2 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="IMAGE",
            position="Right Rail",
            brand="Brand B",
        )
        # Cycle 1: both present
        self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad1, ad2], download_images=False, detected_at="2026-09-23T10:00:00+00:00"
        )

        # Cycle 2: ad1 disappears, ad2 still present
        res2 = self.change_detector.process_detected_advertisements(
            "et_brand_equity", [ad2], scrape_success=True, download_images=False, detected_at="2026-09-23T10:10:00+00:00"
        )
        self.assertEqual(res2["removed"], 1)

        ads = self.repo.get_advertisements(website_key="et_brand_equity")
        ad1_db = next(a for a in ads if a["brand"] == "Brand A")
        ad2_db = next(a for a in ads if a["brand"] == "Brand B")
        self.assertEqual(ad1_db["status"], "REMOVED")
        self.assertEqual(ad2_db["status"], "ACTIVE")

    def test_05_failed_scrape_preserves_active_advertisements(self):
        """5. Failed scrape (scrape_success=False) MUST NOT mark active ads as removed."""
        ad = DetectedAdvertisement(
            website_key="exchange4media",
            page_url="https://www.exchange4media.com/",
            ad_type="BANNER",
            position="Leaderboard",
            brand="HDFC Bank",
        )
        self.change_detector.process_detected_advertisements(
            "exchange4media", [ad], download_images=False
        )

        # Simulate failed scrape returning 0 ads
        res_fail = self.change_detector.process_detected_advertisements(
            "exchange4media", [], scrape_success=False, download_images=False
        )
        self.assertEqual(res_fail["removed"], 0)

        ads = self.repo.get_advertisements(website_key="exchange4media")
        self.assertEqual(len(ads), 1)
        self.assertEqual(ads[0]["status"], "ACTIVE")

    def test_06_publisher_isolation_same_brand_different_sites(self):
        """6. Same brand advertising on both ET and E4M creates isolated distinct records."""
        ad_et = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead",
            brand="Samsung",
        )
        ad_e4m = DetectedAdvertisement(
            website_key="exchange4media",
            page_url="https://www.exchange4media.com/",
            ad_type="BANNER",
            position="Top Masthead",
            brand="Samsung",
        )
        self.change_detector.process_detected_advertisements("et_brand_equity", [ad_et], download_images=False)
        self.change_detector.process_detected_advertisements("exchange4media", [ad_e4m], download_images=False)

        et_ads = self.repo.get_advertisements(website_key="et_brand_equity")
        e4m_ads = self.repo.get_advertisements(website_key="exchange4media")

        self.assertEqual(len(et_ads), 1)
        self.assertEqual(len(e4m_ads), 1)
        self.assertNotEqual(et_ads[0]["website_id"], e4m_ads[0]["website_id"])

    def test_07_kpi_aggregation(self):
        """7. get_advertisement_kpis calculates accurate summary metrics."""
        ad1 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead",
            advertiser="Samsung Electronics",
            brand="Samsung",
        )
        ad2 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="SPONSORED",
            position="Right Rail",
            advertiser="Tata Sons",
            brand="Tata Motors",
        )
        self.change_detector.process_detected_advertisements("et_brand_equity", [ad1, ad2], download_images=False)

        kpis = self.repo.get_advertisement_kpis("et_brand_equity")
        self.assertEqual(kpis["active_ads"], 2)
        self.assertEqual(kpis["total_ads"], 2)
        self.assertEqual(kpis["unique_advertisers"], 2)
        self.assertEqual(kpis["unique_brands"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
