"""
Media Reporting System - Scraper Unit and Integration Verification
Tests URL normalization, article validation, section detection, date parsing,
image filtering, content hash stability, and HTML card extraction.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.base.article import Article
from scraper.et_brand_equity.config import ET_BRAND_EQUITY
from scraper.et_brand_equity.scraper import ETBrandEquityScraper
from scraper.exchange4media.config import EXCHANGE4MEDIA
from scraper.exchange4media.scraper import Exchange4mediaScraper
from scraper.utils.cleaning import clean_image_url, clean_text, is_navigation_text
from scraper.utils.date_parser import parse_date_to_iso
from scraper.utils.url import (
    extract_e4m_article_id,
    extract_e4m_section_slug,
    extract_et_article_id,
    extract_section_slug_from_url,
    is_valid_e4m_article_url,
    is_valid_et_article_url,
    normalize_url,
)


def run_tests() -> bool:
    print("=" * 80)
    print("RUNNING ET BRANDEQUITY SCRAPER VERIFICATION SUITE")
    print("=" * 80)

    passed = 0
    failed = 0

    def assert_true(cond: bool, msg: str):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {msg}")
            passed += 1
        else:
            print(f"  [FAIL] {msg}")
            failed += 1

    # 1. URL Normalization Tests
    print("\n1. Testing URL Normalization & Tracking Parameter Stripping...")
    raw_url = "https://brandequity.economictimes.indiatimes.com/news/marketing/test-slug/134424838?utm_source=top_story&utm_medium=homepage&ref=123#comments"
    expected_url = "https://brandequity.economictimes.indiatimes.com/news/marketing/test-slug/134424838"
    assert_true(
        normalize_url(raw_url) == expected_url,
        "Strips utm_source, utm_medium, ref and hash fragment from article URL",
    )

    rel_url = "/news/digital/another-slug/134424967?utm_source=main_menu"
    base = "https://brandequity.economictimes.indiatimes.com"
    norm_rel = normalize_url(rel_url, base_url=base)
    assert_true(
        norm_rel == "https://brandequity.economictimes.indiatimes.com/news/digital/another-slug/134424967",
        "Resolves relative URL and removes query parameters",
    )

    # 2. Article URL Validation Tests
    print("\n2. Testing Article URL Validation (Distinguishing Articles vs Navigation)...")
    valid_url = "https://brandequity.economictimes.indiatimes.com/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838"
    assert_true(is_valid_et_article_url(valid_url), "Valid article URL with numeric ID passes")

    category_url = "https://brandequity.economictimes.indiatimes.com/news/the-people-report"
    assert_true(not is_valid_et_article_url(category_url), "Category root URL rejected (no numeric ID)")

    menu_url = "https://brandequity.economictimes.indiatimes.com/newsletters"
    assert_true(not is_valid_et_article_url(menu_url), "Newsletter utility URL rejected")

    search_url = "https://brandequity.economictimes.indiatimes.com/news/search/marketing"
    assert_true(not is_valid_et_article_url(search_url), "Search URL rejected")

    ext_url = "https://example.com/news/marketing/article/134424838"
    assert_true(not is_valid_et_article_url(ext_url), "External host URL rejected")

    assert_true(extract_et_article_id(valid_url) == "134424838", "Numeric article ID correctly extracted")

    # 3. Section Detection Tests
    print("\n3. Testing Section Detection...")
    scraper = ETBrandEquityScraper(config=ET_BRAND_EQUITY)
    assert_true(scraper.detect_section(valid_url) == "Marketing", "Detects 'Marketing' section from URL")

    bob_url = "https://brandequity.economictimes.indiatimes.com/news/business-of-brands/slug/134427673"
    assert_true(scraper.detect_section(bob_url) == "Business of Brands", "Detects 'Business of Brands' section")

    tpr_url = "https://brandequity.economictimes.indiatimes.com/news/the-people-report/slug/134426873"
    assert_true(scraper.detect_section(tpr_url) == "The People Report", "Detects 'The People Report' section")

    unknown_url = "https://brandequity.economictimes.indiatimes.com/news/some-topic/slug/134426873"
    assert_true(scraper.detect_section(unknown_url) == "Some Topic", "Capitalizes unrecognized section slugs")

    # 4. Image Filtering Tests
    print("\n4. Testing Image Sanitization...")
    assert_true(clean_image_url("https://example.com/icons/arrow-right.svg") is None, "Rejects SVG icons")
    assert_true(clean_image_url("https://example.com/brandequity-logo.png") is None, "Rejects logo images")
    assert_true(clean_image_url("https://example.com/spacer.gif?width=1&height=1") is None, "Rejects 1x1 tracking pixel")
    real_img = "https://etimg.etb2bimg.com/thumb/img-size-406597/134424967.cms?width=150&height=112"
    assert_true(clean_image_url(real_img) == real_img, "Accepts legitimate content thumbnail image")

    # 5. Date Parsing Tests
    print("\n5. Testing ISO 8601 Date Parsing...")
    rfc_date = "Wed, 23 Sep 2026 08:52:34 +0530"
    iso_result = parse_date_to_iso(rfc_date)
    assert_true(iso_result is not None and "2026-09-23" in iso_result, f"Parsed RFC 2822 date to: {iso_result}")

    sql_date = "2026-09-23 08:52:34"
    iso_sql = parse_date_to_iso(sql_date)
    assert_true(iso_sql is not None and "2026-09-23" in iso_sql, f"Parsed SQL-like date to: {iso_sql}")

    rel_date = "2 hours ago"
    iso_rel = parse_date_to_iso(rel_date)
    assert_true(iso_rel is not None, f"Parsed relative date to: {iso_rel}")

    assert_true(parse_date_to_iso("invalid date text") is None, "Returns None for unparseable date")

    # 6. Content Hash Stability Tests
    print("\n6. Testing SHA-256 Content Hash Stability...")
    art1 = Article(
        website="ET BrandEquity",
        website_key="et_brand_equity",
        section="Marketing",
        headline="Brands want Reddit. They just don’t get it!",
        url="https://brandequity.economictimes.indiatimes.com/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838",
        image_url="https://etimg.etb2bimg.com/thumb/134424838.jpg",
        summary="A summary of the Reddit marketing revolution.",
    ).finalize()

    # Second article created with DIFFERENT scraped_at timestamp
    art2 = Article(
        website="ET BrandEquity",
        website_key="et_brand_equity",
        section="Marketing",
        headline="Brands want Reddit. They just don’t get it!",
        url="https://brandequity.economictimes.indiatimes.com/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838",
        image_url="https://etimg.etb2bimg.com/thumb/134424838.jpg",
        summary="A summary of the Reddit marketing revolution.",
        scraped_at="2026-09-23T12:00:00+00:00",
    ).finalize()

    assert_true(art1.content_hash == art2.content_hash, "Identical content yields identical hash regardless of scraped_at")
    assert_true(len(art1.content_hash) == 64, "Content hash is a valid 64-char SHA-256 hex string")

    # 7. HTML Card Extraction Test
    print("\n7. Testing DOM Card Extraction from HTML Snippet...")
    sample_html = """
    <div class="top-news-wrapper">
        <!-- Genuine Article Card -->
        <article class="news-card">
            <span class="cat-name">Marketing</span>
            <a href="/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838?utm_source=top_story">
                <img data-original="https://etimg.etb2bimg.com/thumb/134424838.jpg" src="/spacer.gif" alt="Reddit preview" />
                <h3>Brands want Reddit. They just don’t get it!</h3>
            </a>
            <p class="summary">Discover how brands are navigating the unique challenges of Reddit engagement.</p>
            <time datetime="2026-09-23T08:52:34+05:30">2 hours ago</time>
        </article>

        <!-- Navigation Menu Item (Must be excluded) -->
        <li class="menu-item">
            <a href="/news/the-people-report?utm_source=main_menu">
                <span>The People Report</span>
            </a>
        </li>

        <!-- Duplicate Article in another section -->
        <div class="featured-card">
            <a href="/news/marketing/brands-want-reddit-they-just-dont-get-it/134424838?utm_source=most_read">
                <h2>Brands want Reddit. They just don’t get it!</h2>
            </a>
        </div>
    </div>
    """
    extracted, candidates, dups = scraper.extract_articles_from_html(
        sample_html,
        page_url="https://brandequity.economictimes.indiatimes.com/",
    )

    assert_true(candidates == 2, f"Found exactly 2 candidate article links (got {candidates})")
    assert_true(len(extracted) == 1, f"Deduplicated to exactly 1 unique article (got {len(extracted)})")
    assert_true(dups == 1, f"Tracked 1 duplicate removed (got {dups})")

    first = extracted[0]
    assert_true(first.headline == "Brands want Reddit. They just don’t get it!", "Correct headline extracted")
    assert_true(first.section == "Marketing", f"Correct section extracted (got {first.section})")
    assert_true(first.image_url == "https://etimg.etb2bimg.com/thumb/134424838.jpg", "Preferred data-original over spacer.gif")
    assert_true("Discover how brands" in (first.summary or ""), "Extracted synopsis paragraph")
    assert_true(first.published_at is not None, f"Parsed time element to ISO: {first.published_at}")

    # 8. Exchange4media URL & Validation Tests (Phase 3)
    print("\n8. Testing Exchange4media URL Validation & Slug Extraction...")
    e4m_valid = "https://www.exchange4media.com/advertising-news/pitch-madison-advertising-report-2026-adex-growth-142801.html?utm_source=home"
    e4m_norm = normalize_url(e4m_valid)
    assert_true(
        e4m_norm == "https://www.exchange4media.com/advertising-news/pitch-madison-advertising-report-2026-adex-growth-142801.html",
        "Normalizes Exchange4media article URL and strips utm tracking parameter",
    )
    assert_true(is_valid_e4m_article_url(e4m_norm), "Validates genuine Exchange4media article URL")

    e4m_cat = "https://www.exchange4media.com/advertising-news"
    assert_true(not is_valid_e4m_article_url(e4m_cat), "Rejects category root without article HTML slug")

    e4m_events = "https://www.exchange4media.com/events/pitch-cmo-summit"
    assert_true(not is_valid_e4m_article_url(e4m_events), "Rejects non-editorial /events path")

    e4m_login = "https://www.exchange4media.com/login"
    assert_true(not is_valid_e4m_article_url(e4m_login), "Rejects utility /login path")

    assert_true(extract_e4m_article_id(e4m_norm) == "142801", "Extracts numeric article ID (142801) from URL")
    assert_true(extract_e4m_section_slug(e4m_norm) == "advertising-news", "Extracts section slug 'advertising-news'")

    # 9. Exchange4media Section Detection Tests
    print("\n9. Testing Exchange4media Section Detection...")
    e4m_scraper = Exchange4mediaScraper(config=EXCHANGE4MEDIA)
    assert_true(e4m_scraper.detect_section(e4m_norm) == "Advertising", "Detects 'Advertising' section from slug")

    mktg_url = "https://www.exchange4media.com/marketing-news/asci-guidelines-ai-142807.html"
    assert_true(e4m_scraper.detect_section(mktg_url) == "Marketing", "Detects 'Marketing' section from slug")

    tv_url = "https://www.exchange4media.com/television-news/connected-tv-ad-142811.html"
    assert_true(e4m_scraper.detect_section(tv_url) == "Television", "Detects 'Television' section from slug")

    # 10. Exchange4media HTML Card Extraction Tests
    print("\n10. Testing Exchange4media DOM Card Extraction...")
    e4m_html = """
    <div class="news-listing">
        <div class="story-item">
            <span class="category-tag">Digital</span>
            <a href="/digital-news/digital-ad-spends-share-surpass-64-percent-2026-142806.html?ref=top">
                <img data-src="https://e4m.gumlet.io/news-photo/142806-digitalgrowth.jpg" src="/spacer.gif" />
                <h3>Digital Advertising Share in India Expected to Surpass 64%</h3>
            </a>
            <p class="desc">Search and retail media networks drive accelerated shift in brand budget allocations.</p>
            <span class="date">Sep 23, 2026</span>
        </div>
        <div class="story-item">
            <a href="/events/upcoming-roundtable">
                <h3>Upcoming Digital Leadership Roundtable</h3>
            </a>
        </div>
    </div>
    """
    e4m_extracted, e4m_cands, e4m_dups = e4m_scraper.extract_articles_from_html(
        e4m_html,
        page_url="https://www.exchange4media.com/",
    )
    assert_true(len(e4m_extracted) == 1, f"Extracted exactly 1 valid E4M article (got {len(e4m_extracted)})")
    e4m_art = e4m_extracted[0]
    assert_true(e4m_art.website_key == "exchange4media", "Website key set to 'exchange4media'")
    assert_true(e4m_art.section == "Digital", f"Detected 'Digital' section (got {e4m_art.section})")
    assert_true(e4m_art.image_url == "https://e4m.gumlet.io/news-photo/142806-digitalgrowth.jpg", "Extracted clean hero image")
    assert_true(len(e4m_art.content_hash) == 64, "Generated valid 64-char SHA-256 content hash")

    # 11. Atomic Card Boundary Isolation & Field Mismatch Prevention Tests
    print("\n11. Testing Atomic Card Boundary Isolation (Anti-Frankenstein)...")
    multi_story_html = """
    <div class="news-listing-wrapper">
        <div class="col-item">
            <a href="/advertising-news/first-brand-story-142801.html">
                <img src="https://e4m.gumlet.io/news-photo/142801-firstbrand.jpg" />
                <h3>First Brand Story Launches Nationwide Campaign</h3>
            </a>
            <p class="desc">First brand story summary detailing the major launch campaign nationwide.</p>
        </div>
        <div class="col-item">
            <a href="/advertising-news/second-brand-story-142802.html">
                <h3>Second Brand Story Incurs Reorganization Changes</h3>
            </a>
            <p class="desc">Second brand story summary explaining internal organizational shifts.</p>
        </div>
    </div>
    """
    ms_extracted, _, _ = e4m_scraper.extract_articles_from_html(
        multi_story_html,
        page_url="https://www.exchange4media.com/",
    )
    assert_true(len(ms_extracted) == 2, f"Extracted both articles from grid (got {len(ms_extracted)})")
    first_art = next(a for a in ms_extracted if "142801" in a.url)
    second_art = next(a for a in ms_extracted if "142802" in a.url)

    assert_true(first_art.headline == "First Brand Story Launches Nationwide Campaign", "First article headline intact")
    assert_true(first_art.image_url == "https://e4m.gumlet.io/news-photo/142801-firstbrand.jpg", "First article has its own image")
    assert_true("First brand story summary" in (first_art.summary or ""), "First article has its own summary")

    assert_true(second_art.headline == "Second Brand Story Incurs Reorganization Changes", "Second article headline intact")
    assert_true(second_art.image_url is None, "Second article does NOT steal first article's image (image_url is None)")
    assert_true("Second brand story summary" in (second_art.summary or ""), "Second article has its own summary without leakage")

    print("-" * 80)
    print(f"VERIFICATION RESULTS: {passed} PASSED, {failed} FAILED")
    print("=" * 80)
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
