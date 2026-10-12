"""
Phase 8B - Storyboard18 and Indian Television Test Suite
Covers 15 tests each for:
  1. Storyboard18 (storyboard18)
  2. Indian Television (indiantelevision)
Plus 5 multi-portal pipeline integration tests (total 35 tests).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root and backend are on sys.path
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scraper.base.article import Article
from scraper.storyboard18 import Storyboard18Scraper, STORYBOARD18
from scraper.indiantelevision import IndianTelevisionScraper, INDIAN_TELEVISION

from scraper.utils.url import (
    is_valid_storyboard18_article_url,
    extract_storyboard18_article_id,
    extract_storyboard18_section_slug,
    is_valid_indiantelevision_article_url,
    extract_indiantelevision_article_id,
    extract_indiantelevision_section_slug,
)


# ===========================================================================
# 1. Storyboard18 Tests (15 tests)
# ===========================================================================
class TestStoryboard18(unittest.TestCase):
    def setUp(self):
        self.scraper = Storyboard18Scraper()

    def test_url_validation_valid_article(self):
        url = "https://www.storyboard18.com/brand-marketing/from-vogue-to-gq-conde-nast-bets-big-on-ai-111547.htm"
        self.assertTrue(is_valid_storyboard18_article_url(url))

    def test_url_validation_advertising_article(self):
        url = "https://www.storyboard18.com/advertising/how-brands-are-navigating-creator-economy-111540.htm"
        self.assertTrue(is_valid_storyboard18_article_url(url))

    def test_url_validation_rejects_category_roots(self):
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/latest-news"))
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/brand-marketing"))
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/advertising"))

    def test_url_validation_rejects_non_article_pages(self):
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/about-us"))
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/privacy-policy"))
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/contact-us"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com/"))
        self.assertFalse(is_valid_storyboard18_article_url("https://www.storyboard18.com"))

    def test_extract_article_id(self):
        url = "https://www.storyboard18.com/brand-marketing/from-vogue-to-gq-111547.htm"
        self.assertEqual(extract_storyboard18_article_id(url), "111547")

    def test_extract_section_slug(self):
        url = "https://www.storyboard18.com/brand-marketing/from-vogue-to-gq-111547.htm"
        self.assertEqual(extract_storyboard18_section_slug(url), "brand-marketing")

    def test_section_detection(self):
        url = "https://www.storyboard18.com/brand-marketing/from-vogue-to-gq-111547.htm"
        self.assertEqual(self.scraper.detect_section(url), "Brand & Marketing")

    def test_headline_extraction(self):
        html = '<div class="news-card"><a href="https://www.storyboard18.com/advertising/festive-campaign-111548.htm"><h2>Top Brands Unveil High Impact Festive Campaigns</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Top Brands Unveil High Impact Festive Campaigns")

    def test_image_extraction_noscript(self):
        html = '''
        <div class="news-card">
            <a href="https://www.storyboard18.com/digital/ai-ad-trends-111549.htm">
                <noscript><img src="https://images.storyboard18.com/lead/ai-trends.jpg" alt="ai" /></noscript>
                <img src="data:image/svg+xml;base64,..." alt="placeholder" />
                <h2>AI Ad Tools Revolutionize Campaign Optimization Across India</h2>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://images.storyboard18.com/lead/ai-trends.jpg")

    def test_summary_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://www.storyboard18.com/agency/independent-agencies-win-pitches-111550.htm">
                <h2>Independent Agencies Win Significant FMCG Accounts in 2026</h2>
            </a>
            <p class="summary-text">Boutique shops are leveraging agile teams and founder-led creative execution to secure key brands.</p>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("Boutique shops are leveraging", articles[0].summary)

    def test_published_date_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://www.storyboard18.com/brand-marketing/luxury-market-grows-111551.htm">
                <h2>Luxury Retail Market Surges in Non-Metro Indian Cities</h2>
            </a>
            <span class="date">Sep 28, 2026, 08:30 AM IST</span>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].published_at.startswith("2026-09-28"))

    def test_exclusive_flag(self):
        html = '<div class="news-card"><a href="https://www.storyboard18.com/agency/exclusive-agency-merger-111552.htm"><h2>EXCLUSIVE: Holding Company in Advanced Merger Talks</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_deduplication(self):
        art1 = Article(
            website="Storyboard18",
            website_key="storyboard18",
            section="Agency",
            headline="Deduplication Article Test on Storyboard18",
            url="https://www.storyboard18.com/agency/dedup-111553.htm",
        ).finalize()
        art2 = Article(
            website="Storyboard18",
            website_key="storyboard18",
            section="Agency",
            headline="Deduplication Article Test on Storyboard18",
            url="https://www.storyboard18.com/agency/dedup-111553.htm",
            summary="Richer updated executive overview of the merger.",
        ).finalize()
        deduped, count = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(count, 1)
        self.assertEqual(deduped[0].summary, "Richer updated executive overview of the merger.")

    def test_scrape_homepage_mocked(self):
        html = '''
        <html><body>
            <div class="news-item">
                <a href="https://www.storyboard18.com/brand-marketing/festive-marketing-trends-111554.htm">
                    <h3>Festive Marketing Spends Poised to Break All Records</h3>
                </a>
            </div>
        </body></html>
        '''
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage(enrich=False)
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 2. Indian Television Tests (15 tests)
# ===========================================================================
class TestIndianTelevision(unittest.TestCase):
    def setUp(self):
        self.scraper = IndianTelevisionScraper()

    def test_url_validation_mam_article(self):
        url = "https://indiantelevision.com/mam/mruci-re-elects-vikram-sakhuja-and-dhruba-mukherjee-as-chairman-and-vice-chairman/"
        self.assertTrue(is_valid_indiantelevision_article_url(url))

    def test_url_validation_television_article(self):
        url = "https://indiantelevision.com/television/broadcast-networks-plan-heavy-programming-slate-for-festive-q3/"
        self.assertTrue(is_valid_indiantelevision_article_url(url))

    def test_url_validation_rejects_category_roots(self):
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/category/mam/"))
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/category/television/"))
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/category/iworld/"))

    def test_url_validation_rejects_non_article_pages(self):
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/about-us/"))
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/feed/"))
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/privacy-policy/"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com/"))
        self.assertFalse(is_valid_indiantelevision_article_url("https://indiantelevision.com"))

    def test_extract_article_id(self):
        url = "https://indiantelevision.com/mam/bajaj-capital-appoints-samir-dewan-as-group-ceo/"
        self.assertEqual(extract_indiantelevision_article_id(url), "bajaj-capital-appoints-samir-dewan-as-group-ceo")

    def test_extract_section_slug(self):
        url = "https://indiantelevision.com/mam/krishna-mishra-joins-etgovernment/"
        self.assertEqual(extract_indiantelevision_section_slug(url), "mam")

    def test_section_detection(self):
        url = "https://indiantelevision.com/iworld/jetsynthesys-and-japans-mixi-sign-mou/"
        self.assertEqual(self.scraper.detect_section(url), "iWorld")

    def test_headline_extraction(self):
        html = '<div class="mvp-feat1-list-cont"><a href="https://indiantelevision.com/mam/filtercopy-comedy-unveils-lineup/"><h2>FilterCopy Comedy Unveils Star Lineup for Mumbai</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "FilterCopy Comedy Unveils Star Lineup for Mumbai")

    def test_image_extraction(self):
        html = '''
        <div class="mvp-feat1-list-cont">
            <a href="https://indiantelevision.com/television/new-show-premiere-in-october/">
                <img src="https://indiantelevision.com/wp-content/uploads/2026/09/show-promo-400x225.jpg" class="wp-post-image" alt="show" />
                <h2>Major GEC Announces Prime Time Fiction Series Premiere</h2>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://indiantelevision.com/wp-content/uploads/2026/09/show-promo-400x225.jpg")

    def test_summary_extraction(self):
        html = '''
        <div class="mvp-widget-feat2-left-cont">
            <a href="https://indiantelevision.com/regulators/trai-issues-new-broadcasting-paper/">
                <h2>TRAI Issues Consultation Paper on National Broadcasting Policy</h2>
            </a>
            <div class="mvp-feat1-feat-text">
                <p>The regulator is seeking comprehensive feedback on audience measurement protocols and infrastructure sharing.</p>
            </div>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("The regulator is seeking", articles[0].summary)

    def test_relative_date_and_category_badge(self):
        html = '''
        <div class="mvp-widget-feat2-right-cont">
            <a href="https://indiantelevision.com/mam/sri-adhikari-brothers-revives-suraag/">
                <div class="mvp-cat-date-wrap">
                    <span class="mvp-cd-cat">Brands</span>
                    <span class="mvp-cd-date">3 hours ago</span>
                </div>
                <h2>Sri Adhikari Brothers Revives Cult Television Classics</h2>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].section, "Brands")
        self.assertEqual(articles[0].publication_label, "3 hours ago")

    def test_exclusive_flag(self):
        html = '<div class="mvp-feat1-list-cont"><a href="https://indiantelevision.com/television/exclusive-broadcaster-slate/"><h2>EXCLUSIVE: Top Broadcaster Announces Overhaul of Regional Slate</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_deduplication(self):
        art1 = Article(
            website="Indian Television",
            website_key="indiantelevision",
            section="Television",
            headline="DTH and Cable Ecosystem Overview",
            url="https://indiantelevision.com/dth/dth-cable-ecosystem-overview/",
        ).finalize()
        art2 = Article(
            website="Indian Television",
            website_key="indiantelevision",
            section="Television",
            headline="DTH and Cable Ecosystem Overview",
            url="https://indiantelevision.com/dth/dth-cable-ecosystem-overview/",
            summary="Comprehensive report on hybrid set top boxes and linear subscriber stability.",
        ).finalize()
        deduped, count = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(count, 1)
        self.assertEqual(deduped[0].summary, "Comprehensive report on hybrid set top boxes and linear subscriber stability.")

    def test_scrape_homepage_mocked(self):
        html = '''
        <html><body>
            <div class="mvp-feat1-list-cont">
                <a href="https://indiantelevision.com/iworld/ott-piracy-framework-announced/">
                    <h2>Digital Streamers and ISPs Form Joint Anti-Piracy Task Force</h2>
                </a>
            </div>
        </body></html>
        '''
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage(enrich=False)
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 3. Nine-Sources Integration Tests (5 tests)
# ===========================================================================
class TestPhase8BNineSourcesIntegration(unittest.TestCase):
    def test_monitored_websites_count_is_9(self):
        from monitoring.engine import MONITORED_WEBSITES
        self.assertEqual(len(MONITORED_WEBSITES), 9)
        keys = [site["key"] for site in MONITORED_WEBSITES]
        self.assertIn("storyboard18", keys)
        self.assertIn("indiantelevision", keys)

    def test_monitoring_status_tracks_all_9_keys(self):
        from monitoring.status import _WEBSITE_KEYS, monitoring_status
        self.assertEqual(len(_WEBSITE_KEYS), 9)
        self.assertIn("storyboard18", _WEBSITE_KEYS)
        self.assertIn("indiantelevision", _WEBSITE_KEYS)
        summary = monitoring_status.get_status_summary()
        self.assertIn("storyboard18", summary["websites"])
        self.assertIn("indiantelevision", summary["websites"])

    def test_change_detector_has_9_default_metadata(self):
        from app.services.change_detector import DEFAULT_WEBSITE_METADATA
        self.assertIn("storyboard18", DEFAULT_WEBSITE_METADATA)
        self.assertIn("indiantelevision", DEFAULT_WEBSITE_METADATA)
        self.assertEqual(DEFAULT_WEBSITE_METADATA["storyboard18"]["name"], "Storyboard18")
        self.assertEqual(DEFAULT_WEBSITE_METADATA["indiantelevision"]["name"], "Indian Television")

    def test_generic_source_service_loads_sb18_and_itv(self):
        from app.services.generic_source_service import load_source_data
        sb18 = load_source_data("storyboard18", "Storyboard18", "https://www.storyboard18.com/")
        self.assertTrue(sb18["is_available"])
        self.assertGreater(sb18["count"], 0)

        itv = load_source_data("indiantelevision", "Indian Television", "https://indiantelevision.com/")
        self.assertTrue(itv["is_available"])
        self.assertGreater(itv["count"], 0)

    def test_dashboard_response_reports_9_websites(self):
        from app.services.mock_data import get_mock_dashboard_data
        dash = get_mock_dashboard_data()
        self.assertEqual(dash.kpis.websites_monitored, 9)
        site_keys = [w.id for w in dash.websites]
        self.assertIn("storyboard18", site_keys)
        self.assertIn("indiantelevision", site_keys)
        self.assertEqual(len(dash.websites), 9)


if __name__ == "__main__":
    unittest.main()
