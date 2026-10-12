"""Regression coverage for intermittent news/ad extraction and persistence failures."""
import asyncio
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database.schema import init_db
from database.repository import Repository
from backend.app.services.ad_change_detector import AdvertisementChangeDetector
from backend.app.services.change_detector import ChangeDetector
from scraper.advertisements import AdvertisementDetector, DetectedAdvertisement
from scraper.base.article import Article
from scraper.base.enrichment import enrich_article, enrich_article_dict
from scraper.base.fetcher import PageFetcher
from scraper.utils.url import (
    is_valid_adgully_article_url,
    is_valid_bestmediainfo_article_url,
    is_valid_e4m_article_url,
    is_valid_social_samosa_article_url,
)


class ExtractionRegressions(unittest.TestCase):
    def test_verified_creative_id_resolves_ad_identity(self):
        ads = AdvertisementDetector("et_brand_equity").detect_advertisements_from_html(
            '<div class="ad-slot"><a href="https://doubleclick.net/click/455385805">'
            '<img src="https://tpc.googlesyndication.com/simgad/2478760894544814965"></a></div>',
            "https://example.com/",
        )
        self.assertEqual(ads[0].brand, "YouTube")
        self.assertEqual(ads[0].campaign, "Festive")

    def test_robots_unavailable_does_not_block_second_request(self):
        fetcher = PageFetcher()
        fetcher.session.get = Mock(return_value=Mock(status_code=404))
        self.assertTrue(fetcher.can_fetch("https://example.com/one"))
        self.assertTrue(fetcher.can_fetch("https://example.com/two"))
        self.assertEqual(fetcher.session.get.call_count, 1)

    def test_lazy_creative_and_relative_click_target(self):
        ads = AdvertisementDetector("exchange4media").detect_advertisements_from_html(
            '<div class="ad-slot"><a href="offers/sale"><img src="data:image/gif;base64,AAA" '
            'data-src="creative.jpg" alt="Adidas"></a></div>', "https://example.com/news/")
        self.assertEqual(ads[0].image_url, "https://example.com/news/creative.jpg")
        self.assertEqual(ads[0].target_url, "https://example.com/news/offers/sale")
        self.assertEqual(ads[0].brand, "Adidas")

    def test_empty_gpt_and_advertorial_navigation_are_not_ads(self):
        html = '<div id="div-gpt-ad-top"></div><nav><div><a href="/advertorial">Advertorial</a></div></nav>'
        self.assertEqual(AdvertisementDetector("exchange4media").detect_advertisements_from_html(html, "https://example.com/"), [])

    def test_graph_metadata_enriches_matching_article_only(self):
        article = Article("Exchange4media", "exchange4media", "Marketing", "A real article headline", "https://example.com/story")
        fetcher = Mock()
        fetcher.fetch_requests.return_value = '''<script type="application/ld+json">{"@graph":[
          {"@type":"NewsArticle","url":"https://example.com/other","description":"Wrong summary"},
          {"@type":"NewsArticle","url":"https://example.com/story","description":"Correct summary",
           "image":{"url":"https://images.example.com/story.jpg"},"datePublished":"2026-09-24T08:00:00Z"}]}</script>'''
        enrich_article(article, fetcher)
        self.assertEqual(article.summary, "Correct summary")
        self.assertIsNotNone(article.image_url)
        self.assertIsNotNone(article.published_at)

    def test_updated_time_is_not_publication_time(self):
        article = Article("ET", "et_brand_equity", "Marketing", "A real article headline", "https://example.com/story")
        fetcher = Mock()
        fetcher.fetch_requests.return_value = '<meta property="og:updated_time" content="2026-09-24T08:00:00Z">'
        self.assertIsNone(enrich_article(article, fetcher).published_at)

    def test_publish_date_meta_is_used_as_publication_time(self):
        article = Article("ET", "et_brand_equity", "Marketing", "A real article headline", "https://example.com/story")
        fetcher = Mock()
        fetcher.fetch_requests.return_value = (
            '<meta name="publish-date" content="Mon, 28 Sep 2026 11:00:19 +0530">'
        )
        enriched = enrich_article(article, fetcher)
        self.assertEqual(enriched.published_at, "2026-09-28T11:00:19+05:30")

    def test_mismatched_canonical_page_does_not_backfill_wrong_story(self):
        fetcher = Mock()
        fetcher.fetch.return_value = (
            '<link rel="canonical" href="https://www.exchange4media.com/marketing-news/other-story-11111.html">'
            '<meta property="article:published_time" content="2026-09-30T10:00:00+05:30">'
            '<h1>Other story headline from redirected page</h1>'
        )
        article = {
            "url": "https://www.exchange4media.com/advertising-news/original-story-22222.html",
            "headline": "Original story headline",
        }
        enriched = enrich_article_dict(article.copy(), fetcher)
        self.assertIsNone(enriched.get("published_at"))
        self.assertEqual(enriched["headline"], "Original story headline")

    def test_problem_listing_urls_are_not_valid_articles(self):
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/date/28-09-2026"))
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/upcoming-events"))
        self.assertTrue(is_valid_adgully_article_url("https://www.adgully.com/post/123456/real-story-slug"))
        self.assertFalse(is_valid_e4m_article_url("https://www.exchange4media.com/advertising-news/category-like-page.html"))
        self.assertFalse(is_valid_e4m_article_url("https://www.exchange4media.com/photo/event-gallery-922.html"))
        self.assertFalse(is_valid_e4m_article_url("https://www.exchange4media.com/trending-topic-ai/airia-leadership-appointment.html"))
        self.assertTrue(is_valid_e4m_article_url("https://www.exchange4media.com/advertising-news/real-story-149157.html"))
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/tags/tv-ratings-policy-2026"))
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/campaign-face-off"))
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/the-pulse-magazine/special-editions-download"))


class PersistenceRegressions(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "test.db"
        init_db(self.db)
        self.repo = Repository(self.db)
        self.ads = AdvertisementChangeDetector(self.repo)

    def tearDown(self):
        self.directory.cleanup()

    def ad(self, name):
        return DetectedAdvertisement("exchange4media", "https://example.com/", "IMAGE", "UNKNOWN", image_url=f"https://images.example.com/{name}.jpg")

    def test_returning_ad_reuses_record_and_first_seen(self):
        self.ads.process_detected_advertisements("exchange4media", [self.ad("a")], download_images=False)
        original = self.repo.get_advertisements()[0]
        self.ads.process_detected_advertisements("exchange4media", [], download_images=False)
        self.ads.process_detected_advertisements("exchange4media", [self.ad("a")], download_images=False)
        rows = self.repo.get_advertisements()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["first_seen_at"], original["first_seen_at"])
        self.assertEqual(rows[0]["status"], "ACTIVE")

    def test_two_creatives_at_unknown_position_do_not_overwrite(self):
        self.ads.process_detected_advertisements("exchange4media", [self.ad("a"), self.ad("b")], download_images=False)
        self.ads.process_detected_advertisements("exchange4media", [self.ad("c"), self.ad("d")], download_images=False)
        active = self.repo.get_advertisements(status="ACTIVE")
        self.assertEqual(len(active), 2)
        self.assertEqual({r["image_url"] for r in active}, {self.ad("c").image_url, self.ad("d").image_url})

    def test_incomplete_observation_preserves_previous_ads(self):
        self.ads.process_detected_advertisements("exchange4media", [self.ad("a")], download_images=False)
        result = self.ads.process_detected_advertisements("exchange4media", [], download_images=False, allow_removals=False)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(len(self.repo.get_advertisements(status="ACTIVE")), 1)

    def test_partial_news_preserves_rich_metadata_and_labels(self):
        detector = ChangeDetector(self.repo)
        article = dict(url="https://example.com/story", headline="Real headline", summary="Full summary", image_url="https://example.com/story.jpg", published_at="2026-09-24T08:00:00Z", is_exclusive=True, publication_label="1 hour ago")
        detector.process_scraped_articles("exchange4media", [article])
        detector.process_scraped_articles("exchange4media", [{**article, "summary": None, "image_url": None, "published_at": None}])
        row = self.repo.get_articles()[0]
        self.assertEqual(row["summary"], "Full summary")
        self.assertEqual(row["image_url"], article["image_url"])
        self.assertEqual(row["is_exclusive"], 1)
        self.assertEqual(row["publication_label"], "1 hour ago")

    def test_database_news_available_without_snapshot(self):
        ChangeDetector(self.repo).process_scraped_articles("exchange4media", [dict(url="https://example.com/story", headline="Real headline")])
        from backend.app.services.exchange4media_service import load_exchange4media_data
        with patch("database.repository.db_repo", self.repo), patch("backend.app.services.exchange4media_service.find_e4m_scraper_output_file", return_value=Path(self.directory.name)/"missing.json"):
            self.assertEqual(load_exchange4media_data()["count"], 1)

    def test_ad_count_filters_match_rows(self):
        first, second = self.ad("a"), self.ad("b")
        first.brand, second.brand = "Alpha", "Beta"
        self.ads.process_detected_advertisements("exchange4media", [first, second], download_images=False)
        self.assertEqual(self.repo.count_advertisements(brand="Alpha"), 1)

    def test_website_ad_route_does_not_pass_query_objects(self):
        from backend.app.api.endpoints import advertisements as endpoint
        with patch.object(endpoint, "db_repo", self.repo):
            result = asyncio.run(endpoint.get_website_advertisements("exchange4media", section=None, status=None, limit=50, skip=0))
        self.assertEqual(result.count, 0)
