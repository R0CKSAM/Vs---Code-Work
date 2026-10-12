"""
Phase 8 - New Media Sources Test Suite
Covers 15 tests each for:
  1. Campaign India (campaign_india)
  2. BestMediaInfo (bestmediainfo)
  3. Social Samosa (social_samosa)
  4. Adgully (adgully)
  5. MediaBrief (mediabrief)
Plus multi-portal pipeline integration tests (total 80 tests).
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
from scraper.campaign_india import CampaignIndiaScraper, CAMPAIGN_INDIA
from scraper.bestmediainfo import BestMediaInfoScraper, BESTMEDIAINFO
from scraper.social_samosa import SocialSamosaScraper, SOCIAL_SAMOSA
from scraper.adgully import AdgullyScraper, ADGULLY
from scraper.mediabrief import MediaBriefScraper, MEDIABRIEF

from scraper.utils.url import (
    is_valid_campaign_india_article_url,
    extract_campaign_india_article_id,
    extract_campaign_india_section_slug,
    is_valid_bestmediainfo_article_url,
    extract_bestmediainfo_article_id,
    extract_bestmediainfo_section_slug,
    is_valid_social_samosa_article_url,
    extract_social_samosa_article_id,
    extract_social_samosa_section_slug,
    is_valid_adgully_article_url,
    extract_adgully_article_id,
    extract_adgully_section_slug,
    is_valid_mediabrief_article_url,
    extract_mediabrief_article_id,
    extract_mediabrief_section_slug,
)


# ===========================================================================
# 1. Campaign India Tests (15 tests)
# ===========================================================================
class TestCampaignIndia(unittest.TestCase):
    def setUp(self):
        self.scraper = CampaignIndiaScraper()

    def test_url_validation_valid_article(self):
        url = "https://www.campaignindia.in/article/top-agency-awards-announced-in-mumbai/498210"
        self.assertTrue(is_valid_campaign_india_article_url(url))

    def test_url_validation_slug_only(self):
        url = "https://www.campaignindia.in/article/ogilvy-secures-major-creative-mandate"
        self.assertTrue(is_valid_campaign_india_article_url(url))

    def test_url_validation_rejects_blocked(self):
        self.assertFalse(is_valid_campaign_india_article_url("https://www.campaignindia.in/login"))
        self.assertFalse(is_valid_campaign_india_article_url("https://www.campaignindia.in/privacy-policy"))
        self.assertFalse(is_valid_campaign_india_article_url("https://www.campaignindia.in/events"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_campaign_india_article_url("https://www.campaignindia.in/news"))
        self.assertFalse(is_valid_campaign_india_article_url("https://www.campaignindia.in/"))

    def test_extract_article_id(self):
        url = "https://www.campaignindia.in/article/awards-2024/498210"
        self.assertEqual(extract_campaign_india_article_id(url), "498210")

    def test_extract_section_slug(self):
        url = "https://www.campaignindia.in/article/advertising/agency-wins-pitch-498210"
        self.assertEqual(extract_campaign_india_section_slug(url), "advertising")

    def test_section_detection(self):
        url = "https://www.campaignindia.in/article/digital/ai-in-brand-marketing-498210"
        self.assertEqual(self.scraper.detect_section(url), "Digital")

    def test_headline_extraction(self):
        html = '<div class="card"><a href="https://www.campaignindia.in/article/test/1234"><h2>Havas Media Wins Mandate For Tech Brand</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Havas Media Wins Mandate For Tech Brand")

    def test_image_extraction(self):
        html = '''
        <div class="card">
            <a href="https://www.campaignindia.in/article/test/1234">
                <img src="https://images.campaignindia.in/hero.jpg" alt="test" />
                <h3>Major Marketing Campaign Launched Today</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://images.campaignindia.in/hero.jpg")

    def test_summary_extraction(self):
        html = '''
        <div class="card">
            <a href="https://www.campaignindia.in/article/test/1234">
                <h3>Major Marketing Campaign Launched Today</h3>
            </a>
            <p class="summary">The new multi-channel initiative will roll out across 15 cities this month.</p>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("multi-channel initiative", articles[0].summary)

    def test_published_date_extraction(self):
        html = '''
        <div class="card">
            <a href="https://www.campaignindia.in/article/test/1234">
                <h3>Major Marketing Campaign Launched Today</h3>
            </a>
            <time datetime="2026-09-28T10:00:00+05:30">28 Sep 2026</time>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].published_at)

    def test_exclusive_flag(self):
        html = '''
        <div class="card">
            <span class="badge">Exclusive</span>
            <a href="https://www.campaignindia.in/article/test/1234">
                <h3>Major Marketing Campaign Launched Today</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_atomic_card_isolation(self):
        html = '''
        <div class="wrapper">
            <div class="card1">
                <a href="https://www.campaignindia.in/article/card-one/1111"><h3>First Headline For Campaign India</h3></a>
                <p>Summary for card one is completely distinct.</p>
            </div>
            <div class="card2">
                <a href="https://www.campaignindia.in/article/card-two/2222"><h3>Second Headline For Campaign India</h3></a>
                <p>Summary for card two is completely distinct.</p>
            </div>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 2)
        self.assertIn("card one", articles[0].summary)
        self.assertIn("card two", articles[1].summary)

    def test_deduplication(self):
        art1 = Article(website="Campaign India", website_key="campaign_india", section="News",
                       headline="Headline Testing Deduplication", url="https://www.campaignindia.in/article/test/1234").finalize()
        art2 = Article(website="Campaign India", website_key="campaign_india", section="News",
                       headline="Headline Testing Deduplication", url="https://www.campaignindia.in/article/test/1234",
                       summary="Rich summary added later").finalize()
        deduped, removed = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(removed, 1)
        self.assertEqual(deduped[0].summary, "Rich summary added later")

    def test_scrape_homepage_mocked(self):
        html = '<div class="card"><a href="https://www.campaignindia.in/article/live/5555"><h3>Breaking News Live In Advertising</h3></a></div>'
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage()
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)
            self.assertGreaterEqual(stats["pages_fetched"], 1)


# ===========================================================================
# 2. BestMediaInfo Tests (15 tests)
# ===========================================================================
class TestBestMediaInfo(unittest.TestCase):
    def setUp(self):
        self.scraper = BestMediaInfoScraper()

    def test_url_validation_dated(self):
        url = "https://bestmediainfo.com/2026/09/top-broadcaster-revenue-jumps-in-q2"
        self.assertTrue(is_valid_bestmediainfo_article_url(url))

    def test_url_validation_post_format(self):
        url = "https://bestmediainfo.com/post/wpp-announces-new-leadership-team"
        self.assertTrue(is_valid_bestmediainfo_article_url(url))

    def test_url_validation_rejects_blocked(self):
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/about-us"))
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/privacy-policy"))
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/contact-us"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/"))
        self.assertFalse(is_valid_bestmediainfo_article_url("https://bestmediainfo.com/home"))

    def test_extract_article_id(self):
        url = "https://bestmediainfo.com/2026/09/sony-pictures-signs-ad-deal-78492"
        self.assertEqual(extract_bestmediainfo_article_id(url), "78492")

    def test_extract_section_slug(self):
        url = "https://bestmediainfo.com/advertising/festive-ad-spends-set-to-grow"
        self.assertEqual(extract_bestmediainfo_section_slug(url), "advertising")

    def test_section_detection(self):
        url = "https://bestmediainfo.com/television/broadcast-rating-council-update"
        self.assertEqual(self.scraper.detect_section(url), "Television")

    def test_headline_extraction(self):
        html = '<div class="news-card"><a href="https://bestmediainfo.com/2026/09/zee-entertainment-profit-soars"><h2>Zee Entertainment Profit Soars in Q2</h2></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Zee Entertainment Profit Soars in Q2")

    def test_image_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://bestmediainfo.com/2026/09/zee-entertainment-profit-soars">
                <img src="https://bestmediainfo.com/uploads/zee.jpg" alt="zee" />
                <h3>Zee Entertainment Profit Soars in Q2</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://bestmediainfo.com/uploads/zee.jpg")

    def test_summary_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://bestmediainfo.com/2026/09/zee-entertainment-profit-soars">
                <h3>Zee Entertainment Profit Soars in Q2</h3>
            </a>
            <div class="summary">The broadcaster reported strong digital and ad revenue growth for the quarter.</div>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("strong digital and ad revenue", articles[0].summary)

    def test_published_date(self):
        html = '''
        <div class="news-card">
            <a href="https://bestmediainfo.com/2026/09/zee-entertainment-profit-soars">
                <h3>Zee Entertainment Profit Soars in Q2</h3>
            </a>
            <span class="date">September 28, 2026</span>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].published_at)

    def test_exclusive_flag(self):
        html = '''
        <div class="news-card">
            <span class="badge">Exclusive: Industry Scoop</span>
            <a href="https://bestmediainfo.com/2026/09/zee-entertainment-profit-soars">
                <h3>Zee Entertainment Profit Soars in Q2</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_atomic_card_isolation(self):
        html = '''
        <div class="feed">
            <div class="item1"><a href="https://bestmediainfo.com/2026/09/first-item-reported"><h3>First Item Reported On BestMediaInfo</h3></a><p>Summary for first article content.</p></div>
            <div class="item2"><a href="https://bestmediainfo.com/2026/09/second-item-reported"><h3>Second Item Reported On BestMediaInfo</h3></a><p>Summary for second article content.</p></div>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 2)
        self.assertIn("first article", articles[0].summary)
        self.assertIn("second article", articles[1].summary)

    def test_deduplication(self):
        art1 = Article(website="BestMediaInfo", website_key="bestmediainfo", section="Media",
                       headline="Deduplication Verification Article", url="https://bestmediainfo.com/2026/09/dedup-article").finalize()
        art2 = Article(website="BestMediaInfo", website_key="bestmediainfo", section="Media",
                       headline="Deduplication Verification Article", url="https://bestmediainfo.com/2026/09/dedup-article",
                       image_url="https://bestmediainfo.com/rich.jpg").finalize()
        deduped, removed = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(removed, 1)
        self.assertEqual(deduped[0].image_url, "https://bestmediainfo.com/rich.jpg")

    def test_scrape_homepage_mocked(self):
        html = '<div class="news-card"><a href="https://bestmediainfo.com/2026/09/ad-growth-trends"><h3>Indian Ad Spends Hit Record High</h3></a></div>'
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage()
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 3. Social Samosa Tests (15 tests)
# ===========================================================================
class TestSocialSamosa(unittest.TestCase):
    def setUp(self):
        self.scraper = SocialSamosaScraper()

    def test_url_validation_dated(self):
        url = "https://www.socialsamosa.com/2026/09/instagram-algorithm-updates-for-brands/"
        self.assertTrue(is_valid_social_samosa_article_url(url))

    def test_url_validation_slug(self):
        url = "https://www.socialsamosa.com/festive-marketing-campaigns-breakdown/"
        self.assertTrue(is_valid_social_samosa_article_url(url))

    def test_url_validation_rejects_blocked(self):
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/about-us/"))
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/privacy-policy/"))
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/events/"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/"))
        self.assertFalse(is_valid_social_samosa_article_url("https://www.socialsamosa.com/feed/"))

    def test_extract_article_id(self):
        url = "https://www.socialsamosa.com/2026/09/swiggy-social-media-strategy/"
        self.assertEqual(extract_social_samosa_article_id(url), "swiggy-social-media-strategy")

    def test_extract_section_slug(self):
        url = "https://www.socialsamosa.com/campaigns/zomato-viral-marketing-campaign/"
        self.assertEqual(extract_social_samosa_section_slug(url), "campaigns")

    def test_section_detection(self):
        url = "https://www.socialsamosa.com/case-studies/meta-ad-strategy/"
        self.assertEqual(self.scraper.detect_section(url), "Case Studies")

    def test_headline_extraction(self):
        html = '<article><a href="https://www.socialsamosa.com/2026/09/swiggy-campaign-review/"><h1>Swiggy Rolls Out Viral Meme Campaign</h1></a></article>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Swiggy Rolls Out Viral Meme Campaign")

    def test_image_extraction(self):
        html = '''
        <article>
            <a href="https://www.socialsamosa.com/2026/09/swiggy-campaign-review/">
                <img data-src="https://www.socialsamosa.com/wp-content/uploads/swiggy.jpg" alt="swiggy" />
                <h2>Swiggy Rolls Out Viral Meme Campaign</h2>
            </a>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://www.socialsamosa.com/wp-content/uploads/swiggy.jpg")

    def test_summary_extraction(self):
        html = '''
        <article>
            <a href="https://www.socialsamosa.com/2026/09/swiggy-campaign-review/">
                <h2>Swiggy Rolls Out Viral Meme Campaign</h2>
            </a>
            <div class="entry-summary">A deep dive into how humor and pop culture drove record app downloads.</div>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("humor and pop culture", articles[0].summary)

    def test_published_date(self):
        html = '''
        <article>
            <a href="https://www.socialsamosa.com/2026/09/swiggy-campaign-review/">
                <h2>Swiggy Rolls Out Viral Meme Campaign</h2>
            </a>
            <time datetime="2026-09-28T09:30:00Z">September 28, 2026</time>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].published_at)

    def test_exclusive_flag(self):
        html = '''
        <article>
            <span class="badge">Exclusive</span>
            <a href="https://www.socialsamosa.com/2026/09/swiggy-campaign-review/">
                <h2>Swiggy Rolls Out Viral Meme Campaign</h2>
            </a>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_atomic_card_isolation(self):
        html = '''
        <div class="posts">
            <article class="p1"><a href="https://www.socialsamosa.com/2026/09/post-one-insight/"><h2>First Post Insights on Social Samosa</h2></a><p>First excerpt details here.</p></article>
            <article class="p2"><a href="https://www.socialsamosa.com/2026/09/post-two-insight/"><h2>Second Post Insights on Social Samosa</h2></a><p>Second excerpt details here.</p></article>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 2)
        self.assertIn("First excerpt", articles[0].summary)
        self.assertIn("Second excerpt", articles[1].summary)

    def test_deduplication(self):
        art1 = Article(website="Social Samosa", website_key="social_samosa", section="Campaigns",
                       headline="Deduplication Article Social Samosa", url="https://www.socialsamosa.com/2026/09/dedup-post/").finalize()
        art2 = Article(website="Social Samosa", website_key="social_samosa", section="Campaigns",
                       headline="Deduplication Article Social Samosa", url="https://www.socialsamosa.com/2026/09/dedup-post/",
                       summary="Updated richer description").finalize()
        deduped, removed = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(removed, 1)
        self.assertEqual(deduped[0].summary, "Updated richer description")

    def test_scrape_homepage_mocked(self):
        html = '<article><a href="https://www.socialsamosa.com/2026/09/influencer-trends/"><h3>Top Influencer Marketing Trends 2026</h3></a></article>'
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage()
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 4. Adgully Tests (15 tests)
# ===========================================================================
class TestAdgully(unittest.TestCase):
    def setUp(self):
        self.scraper = AdgullyScraper()

    def test_url_validation_numeric_id(self):
        url = "https://www.adgully.com/havells-launches-festive-campaign-145829.html"
        self.assertTrue(is_valid_adgully_article_url(url))

    def test_url_validation_section_path(self):
        url = "https://www.adgully.com/marketing/new-brand-strategy-announced-145830.html"
        self.assertTrue(is_valid_adgully_article_url(url))

    def test_url_validation_rejects_blocked(self):
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/about-us"))
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/privacy-policy"))
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/awards"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/"))
        self.assertFalse(is_valid_adgully_article_url("https://www.adgully.com/index.html"))

    def test_extract_article_id(self):
        url = "https://www.adgully.com/creative-agency-wins-pitch-145829.html"
        self.assertEqual(extract_adgully_article_id(url), "145829")

    def test_extract_section_slug(self):
        url = "https://www.adgully.com/marketing/festive-season-growth-145831.html"
        self.assertEqual(extract_adgully_section_slug(url), "marketing")

    def test_section_detection(self):
        url = "https://www.adgully.com/exclusives/inside-scoop-on-brand-merger-145832.html"
        self.assertEqual(self.scraper.detect_section(url), "Exclusives")

    def test_headline_extraction(self):
        html = '<div class="news-card"><a href="https://www.adgully.com/titan-watches-festive-145833.html"><h3>Titan Launches Stunning New Campaign</h3></a></div>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Titan Launches Stunning New Campaign")

    def test_image_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://www.adgully.com/titan-watches-festive-145833.html">
                <img src="https://static.adgully.com/titan.jpg" alt="titan" />
                <h3>Titan Launches Stunning New Campaign</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://static.adgully.com/titan.jpg")

    def test_summary_extraction(self):
        html = '''
        <div class="news-card">
            <a href="https://www.adgully.com/titan-watches-festive-145833.html">
                <h3>Titan Launches Stunning New Campaign</h3>
            </a>
            <p class="desc">The festive film highlights timeless connections across generations.</p>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("timeless connections", articles[0].summary)

    def test_published_date(self):
        html = '''
        <div class="news-card">
            <a href="https://www.adgully.com/titan-watches-festive-145833.html">
                <h3>Titan Launches Stunning New Campaign</h3>
            </a>
            <time datetime="2026-09-28T11:00:00+05:30">28 Sep 2026</time>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].published_at)

    def test_exclusive_flag_from_headline(self):
        html = '''
        <div class="news-card">
            <a href="https://www.adgully.com/exclusive-industry-shakeup-145834.html">
                <h3>EXCLUSIVE: Leading FMCG Brand Realigns Media Account</h3>
            </a>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_atomic_card_isolation(self):
        html = '''
        <div class="container">
            <div class="card_a"><a href="https://www.adgully.com/story-one-145835.html"><h3>Story One On Adgully Platform</h3></a><p>Summary for story one explicitly.</p></div>
            <div class="card_b"><a href="https://www.adgully.com/story-two-145836.html"><h3>Story Two On Adgully Platform</h3></a><p>Summary for story two explicitly.</p></div>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 2)
        self.assertIn("story one", articles[0].summary)
        self.assertIn("story two", articles[1].summary)

    def test_deduplication(self):
        art1 = Article(website="Adgully", website_key="adgully", section="Marketing",
                       headline="Adgully Article Deduplication Test", url="https://www.adgully.com/dedup-145837.html").finalize()
        art2 = Article(website="Adgully", website_key="adgully", section="Marketing",
                       headline="Adgully Article Deduplication Test", url="https://www.adgully.com/dedup-145837.html",
                       is_exclusive=True).finalize()
        deduped, removed = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(removed, 1)
        self.assertTrue(deduped[0].is_exclusive)

    def test_scrape_homepage_mocked(self):
        html = '<div class="news-card"><a href="https://www.adgully.com/breaking-ad-deal-145838.html"><h3>New Mega Media Deal Struck in Mumbai</h3></a></div>'
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage()
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 5. MediaBrief Tests (15 tests)
# ===========================================================================
class TestMediaBrief(unittest.TestCase):
    def setUp(self):
        self.scraper = MediaBriefScraper()

    def test_url_validation_standard(self):
        url = "https://mediabrief.com/netflix-announces-new-content-slate-india/"
        self.assertTrue(is_valid_mediabrief_article_url(url))

    def test_url_validation_dated(self):
        url = "https://mediabrief.com/2026/09/hotstar-disney-viewership-report/"
        self.assertTrue(is_valid_mediabrief_article_url(url))

    def test_url_validation_rejects_blocked(self):
        self.assertFalse(is_valid_mediabrief_article_url("https://mediabrief.com/about-us/"))
        self.assertFalse(is_valid_mediabrief_article_url("https://mediabrief.com/privacy-policy/"))
        self.assertFalse(is_valid_mediabrief_article_url("https://mediabrief.com/podcasts/"))

    def test_url_validation_rejects_root(self):
        self.assertFalse(is_valid_mediabrief_article_url("https://mediabrief.com/"))
        self.assertFalse(is_valid_mediabrief_article_url("https://mediabrief.com/feed/"))

    def test_extract_article_id(self):
        url = "https://mediabrief.com/exclusive-broadcast-rights-awarded/"
        self.assertEqual(extract_mediabrief_article_id(url), "exclusive-broadcast-rights-awarded")

    def test_extract_section_slug(self):
        url = "https://mediabrief.com/advertising/festive-brand-campaigns-roundup/"
        self.assertEqual(extract_mediabrief_section_slug(url), "advertising")

    def test_section_detection(self):
        url = "https://mediabrief.com/exclusive/interview-with-broadcaster-ceo/"
        self.assertEqual(self.scraper.detect_section(url), "Exclusive")

    def test_headline_extraction(self):
        html = '<article><a href="https://mediabrief.com/prime-video-subscribers-reach-peak/"><h2>Prime Video Viewership Breaks All Records</h2></a></article>'
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].headline, "Prime Video Viewership Breaks All Records")

    def test_image_extraction(self):
        html = '''
        <article>
            <a href="https://mediabrief.com/prime-video-subscribers-reach-peak/">
                <img src="https://mediabrief.com/wp-content/uploads/prime.jpg" alt="prime" />
                <h2>Prime Video Viewership Breaks All Records</h2>
            </a>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].image_url, "https://mediabrief.com/wp-content/uploads/prime.jpg")

    def test_summary_extraction(self):
        html = '''
        <article>
            <a href="https://mediabrief.com/prime-video-subscribers-reach-peak/">
                <h2>Prime Video Viewership Breaks All Records</h2>
            </a>
            <div class="entry-summary">Streaming hours increased 35 percent year over year across regional languages.</div>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertIn("Streaming hours increased", articles[0].summary)

    def test_published_date_preserved_with_exclusive(self):
        # Critical test: exclusive badge must NOT destroy published_at
        html = '''
        <article>
            <span class="badge">Exclusive</span>
            <a href="https://mediabrief.com/prime-video-subscribers-reach-peak/">
                <h2>Prime Video Viewership Breaks All Records</h2>
            </a>
            <time datetime="2026-09-28T08:00:00+05:30">September 28, 2026</time>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)
        self.assertIsNotNone(articles[0].published_at)
        self.assertIn("2026-09-28", articles[0].published_at)

    def test_exclusive_from_section_path(self):
        html = '''
        <article>
            <a href="https://mediabrief.com/exclusive/inside-broadcaster-deal/">
                <h2>Exclusive Report On Mega Studio Acquisition</h2>
            </a>
        </article>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].is_exclusive)

    def test_atomic_card_isolation(self):
        html = '''
        <div class="grid">
            <article class="first"><a href="https://mediabrief.com/first-story-analysis/"><h2>First Story Headline In Brief</h2></a><p>First article description text.</p></article>
            <article class="second"><a href="https://mediabrief.com/second-story-analysis/"><h2>Second Story Headline In Brief</h2></a><p>Second article description text.</p></article>
        </div>
        '''
        articles, _, _ = self.scraper.extract_articles_from_html(html)
        self.assertEqual(len(articles), 2)
        self.assertIn("First article", articles[0].summary)
        self.assertIn("Second article", articles[1].summary)

    def test_deduplication(self):
        art1 = Article(website="MediaBrief", website_key="mediabrief", section="Media",
                       headline="MediaBrief Deduplication Test", url="https://mediabrief.com/dedup-test/").finalize()
        art2 = Article(website="MediaBrief", website_key="mediabrief", section="Media",
                       headline="MediaBrief Deduplication Test", url="https://mediabrief.com/dedup-test/",
                       published_at="2026-09-28T12:00:00+05:30").finalize()
        deduped, removed = self.scraper.deduplicate_articles([art1, art2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(removed, 1)
        self.assertIsNotNone(deduped[0].published_at)

    def test_scrape_homepage_mocked(self):
        html = '<article><a href="https://mediabrief.com/new-podcast-launch/"><h3>Podcast Network Expands Across Five Languages</h3></a></article>'
        with patch.object(self.scraper.fetcher, "fetch", return_value=html):
            articles, stats = self.scraper.scrape_homepage()
            self.assertEqual(len(articles), 1)
            self.assertEqual(stats["valid_articles"], 1)


# ===========================================================================
# 6. Pipeline Integration & Registration Tests (5 tests)
# ===========================================================================
class TestPhase8PipelineIntegration(unittest.TestCase):
    def test_monitored_websites_count_is_seven(self):
        from monitoring.engine import MONITORED_WEBSITES
        self.assertEqual(len(MONITORED_WEBSITES), 7)
        keys = {s["key"] for s in MONITORED_WEBSITES}
        expected = {
            "et_brand_equity",
            "exchange4media",
            "campaign_india",
            "bestmediainfo",
            "social_samosa",
            "adgully",
            "mediabrief",
        }
        self.assertEqual(keys, expected)

    def test_scraper_dispatch_all_seven(self):
        from monitoring.engine import _scrape_website
        for site_key in [
            "et_brand_equity",
            "exchange4media",
            "campaign_india",
            "bestmediainfo",
            "social_samosa",
            "adgully",
            "mediabrief",
        ]:
            # Mock the scraper instance so we don't hit the internet in unit tests
            dummy_art = Article(website="Test", website_key=site_key, section="Test",
                                headline="Dummy Headline With Sufficient Length For Test",
                                url=f"https://{site_key}.com/test-article").finalize()
            with patch("scraper.base.fetcher.PageFetcher.fetch", return_value=None):
                with patch.object(CampaignIndiaScraper, "scrape_homepage", return_value=([dummy_art], {})):
                    with patch.object(BestMediaInfoScraper, "scrape_homepage", return_value=([dummy_art], {})):
                        with patch.object(SocialSamosaScraper, "scrape_homepage", return_value=([dummy_art], {})):
                            with patch.object(AdgullyScraper, "scrape_homepage", return_value=([dummy_art], {})):
                                with patch.object(MediaBriefScraper, "scrape_homepage", return_value=([dummy_art], {})):
                                    arts, ok, err = _scrape_website(site_key)
                                    if site_key in ("campaign_india", "bestmediainfo", "social_samosa", "adgully", "mediabrief"):
                                        self.assertTrue(ok)
                                        self.assertEqual(len(arts), 1)

    def test_monitoring_status_has_seven_sites(self):
        from monitoring.status import monitoring_status
        snap = monitoring_status.snapshot()
        self.assertEqual(len(snap["websites"]), 7)
        self.assertIn("campaign_india", snap["websites"])
        self.assertIn("bestmediainfo", snap["websites"])
        self.assertIn("social_samosa", snap["websites"])
        self.assertIn("adgully", snap["websites"])
        self.assertIn("mediabrief", snap["websites"])

    def test_change_detector_metadata_has_seven_sites(self):
        from app.services.change_detector import DEFAULT_WEBSITE_METADATA
        self.assertEqual(len(DEFAULT_WEBSITE_METADATA), 7)
        self.assertIn("campaign_india", DEFAULT_WEBSITE_METADATA)
        self.assertIn("bestmediainfo", DEFAULT_WEBSITE_METADATA)
        self.assertIn("social_samosa", DEFAULT_WEBSITE_METADATA)
        self.assertIn("adgully", DEFAULT_WEBSITE_METADATA)
        self.assertIn("mediabrief", DEFAULT_WEBSITE_METADATA)

    def test_api_routes_registered(self):
        from app.api.endpoints import (
            api_router,
            campaign_india_articles_router,
            bestmediainfo_articles_router,
            social_samosa_articles_router,
            adgully_articles_router,
            mediabrief_articles_router,
        )

        # 1. Verify parent api_router exists
        self.assertIsNotNone(api_router)

        # 2. Verify each source router prefix
        expected_prefixes = {
            "campaign_india": ("/monitoring/campaign-india", campaign_india_articles_router),
            "bestmediainfo": ("/monitoring/bestmediainfo", bestmediainfo_articles_router),
            "social_samosa": ("/monitoring/social-samosa", social_samosa_articles_router),
            "adgully": ("/monitoring/adgully", adgully_articles_router),
            "mediabrief": ("/monitoring/mediabrief", mediabrief_articles_router),
        }

        for site_key, (expected_prefix, router) in expected_prefixes.items():
            self.assertEqual(router.prefix, expected_prefix, f"Prefix mismatch for {site_key}")
            self.assertGreaterEqual(len(router.routes), 2, f"Router for {site_key} should have at least 2 routes")
            route_paths = [getattr(r, "path", "") for r in router.routes]
            self.assertTrue(
                any("/articles" in p for p in route_paths),
                f"Missing /articles route for {site_key} (found {route_paths})",
            )
            self.assertTrue(
                any("/refresh" in p for p in route_paths),
                f"Missing /refresh route for {site_key} (found {route_paths})",
            )


if __name__ == "__main__":
    unittest.main()
