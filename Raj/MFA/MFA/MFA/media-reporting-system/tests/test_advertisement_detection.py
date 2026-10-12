"""
Phase 6 - Advertisement Detection Unit Tests
Tests multi-signal advertisement detection and false-positive prevention with HTML fixtures.
"""
import sys
import unittest
from pathlib import Path

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scraper.advertisements import AdvertisementDetector, DetectedAdvertisement


class TestAdvertisementDetection(unittest.TestCase):

    def setUp(self):
        self.detector = AdvertisementDetector("et_brand_equity")

    def test_01_detect_banner_ad(self):
        """1. Image banner ad inside a recognized ad slot is detected."""
        html = """
        <html>
          <body>
            <div id="div-gpt-ad-12345-0" class="ad-slot top-banner" data-advertiser="Samsung" data-brand="Galaxy S26">
              <a href="https://www.samsung.com/in/smartphones/galaxy-s26">
                <img src="https://images.samsung.com/banner-970x250.jpg" alt="Galaxy S26 Launch">
              </a>
            </div>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 1)
        ad = ads[0]
        self.assertIn(ad.ad_type, ["BANNER", "IMAGE"])
        self.assertIn("Top Masthead", ad.position)
        self.assertEqual(ad.advertiser, "Samsung")
        self.assertEqual(ad.brand, "Galaxy S26")
        self.assertEqual(ad.image_url, "https://images.samsung.com/banner-970x250.jpg")
        self.assertTrue(len(ad.ad_hash) == 64)

    def test_02_detect_sponsored_block(self):
        """2. Sponsored content card is detected as SPONSORED."""
        html = """
        <html>
          <body>
            <div class="sponsored-content sponsor-card" data-brand="Tata Motors EV">
              <div class="sponsor-label">Sponsored</div>
              <a href="https://www.tatamotors.com/ev-campaign">
                <img src="https://media.tatamotors.com/curvv-ev-300x250.jpg" alt="Drive the Future">
              </a>
            </div>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 1)
        ad = ads[0]
        self.assertEqual(ad.ad_type, "SPONSORED")
        self.assertEqual(ad.brand, "Tata Motors EV")

    def test_03_detect_iframe_ad(self):
        """3. Iframe ad placement is detected as IFRAME."""
        html = """
        <html>
          <body>
            <div class="sidebar-ad right-rail">
              <iframe id="google_ads_iframe_sidebar_0" src="https://doubleclick.net/ad?slot=right_rail" width="300" height="600"></iframe>
            </div>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://www.exchange4media.com/")
        self.assertEqual(len(ads), 1)
        ad = ads[0]
        self.assertEqual(ad.ad_type, "IFRAME")
        self.assertIn("Right", ad.position)

    def test_04_editorial_hero_image_not_classified_as_ad(self):
        """4. Editorial article hero image inside <article> must NOT be classified as an ad."""
        html = """
        <html>
          <body>
            <article class="news-card">
              <h1 class="headline">Joy Personal Care ropes in Tamannaah Bhatia</h1>
              <div class="featured-image">
                <img src="https://etimg.etb2bimg.com/thumb/tamannaah.jpg" alt="Tamannaah Bhatia Joy Personal Care">
              </div>
              <p class="summary">Joy Personal Care has announced its latest campaign...</p>
            </article>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 0, "Editorial hero image was falsely classified as an ad!")

    def test_05_header_logo_not_classified_as_ad(self):
        """5. Site logo in header must NOT be classified as an ad."""
        html = """
        <html>
          <body>
            <header>
              <div class="site-logo">
                <a href="/" class="navbar-brand">
                  <img src="https://brandequity.economictimes.indiatimes.com/images/et-logo.png" alt="ET BrandEquity Logo">
                </a>
              </div>
            </header>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 0, "Site logo was falsely classified as an ad!")

    def test_06_navigation_icons_and_avatar_not_classified(self):
        """6. Author avatar and navigation icons must NOT be classified as an ad."""
        html = """
        <html>
          <body>
            <nav class="main-navigation">
              <a href="/news"><img src="/icons/news-icon.svg" alt="News"></a>
            </nav>
            <div class="byline">
              <img class="author-avatar" src="/authors/editor.jpg" alt="Senior Editor">
              <span>By Senior Editor</span>
            </div>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://www.exchange4media.com/")
        self.assertEqual(len(ads), 0, "Author avatar/nav icon was falsely classified as an ad!")

    def test_07_deterministic_hash_same_ad(self):
        """7. Deterministic ad hash is stable across multiple detections."""
        ad1 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            advertiser="Samsung",
            brand="Samsung Galaxy",
            image_url="https://images.samsung.com/banner.jpg",
            target_url="https://samsung.com",
        )
        ad2 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            advertiser="Samsung",
            brand="Samsung Galaxy",
            image_url="https://images.samsung.com/banner.jpg",
            target_url="https://samsung.com",
        )
        self.assertEqual(ad1.compute_hash(), ad2.compute_hash())

    def test_08_changed_creative_different_hash(self):
        """8. Changed creative image produces a distinct ad hash."""
        ad1 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            image_url="https://images.samsung.com/banner_v1.jpg",
        )
        ad2 = DetectedAdvertisement(
            website_key="et_brand_equity",
            page_url="https://brandequity.economictimes.indiatimes.com/",
            ad_type="BANNER",
            position="Top Masthead Billboard",
            image_url="https://images.samsung.com/banner_v2.jpg",
        )
        self.assertNotEqual(ad1.compute_hash(), ad2.compute_hash())

    def test_09_unresolved_advertiser_is_none_not_fabricated(self):
        """9. When advertiser is not detectable, it remains None rather than fabricated."""
        html = """
        <html>
          <body>
            <div class="ad-slot right-rail">
              <a href="https://adclick.g.doubleclick.net/pcs/click?xai=123">
                <img src="https://creative.serving.com/ad300x250.png" alt="Advertisement">
              </a>
            </div>
          </body>
        </html>
        """
        ads = self.detector.detect_advertisements_from_html(html, "https://brandequity.economictimes.indiatimes.com/")
        self.assertEqual(len(ads), 1)
        # Should NOT fabricate names like 'Google' or fake brand names from ad tech URLs
        self.assertIsNone(ads[0].brand)

    def test_10_standard_creative_dimensions_resolve_position(self):
        """Rendered frames without slot classes use standard dimensions for placement."""
        top = self.detector.detect_advertisements_from_html(
            '<iframe id="google_ads_iframe_1" src="https://doubleclick.net/ad" width="728" height="90"></iframe>',
            "https://example.com/",
        )[0]
        side = self.detector.detect_advertisements_from_html(
            '<iframe id="google_ads_iframe_2" src="https://doubleclick.net/ad" width="300" height="250"></iframe>',
            "https://example.com/",
        )[0]
        self.assertEqual(top.position, "Top Masthead Billboard")
        self.assertEqual(side.position, "Right Sidebar MPU")


if __name__ == "__main__":
    unittest.main(verbosity=2)
