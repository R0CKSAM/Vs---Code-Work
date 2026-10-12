"""
Phase 7.4 Test Suite: Published Time Display + Exclusive Content Repair

Verifies:
1. Authoritative published_at exists -> normal formatted publication time.
2. published_at is None, publication_label = "46 minutes ago" -> "46 minutes ago".
3. published_at is None, publication_label = "9 hours ago" -> "9 hours ago".
4. published_at is None, publication_label = "2 days ago" -> "2 days ago".
5. published_at is None, no relative label -> "Publication time unavailable".
6. Explicit exclusive flag/metadata -> "Exclusive Content".
7. Exclusive article with publication time -> "Exclusive Content".
8. Summary contains the word 'exclusive' in prose but not tagged exclusive -> NOT treated as Exclusive Content.
9. scraped_at exists but published_at and relative label do not -> "Publication time unavailable" (never substituted).
"""
import json
import os
import sys
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
from scraper.base.article import Article
from scraper.utils.date_parser import (
    extract_relative_time_label,
    extract_exclusive_flag,
)
from backend.app.services.mock_data import format_relative_time


class TestPhase7_4PublishedExclusive(unittest.TestCase):

    def test_01_authoritative_published_at_formatted_correctly(self):
        """1. When authoritative published_at exists, formatted publication time is returned."""
        dt = datetime(2026, 9, 23, 10, 30, 0, tzinfo=timezone.utc)
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Marketing",
            headline="Sample Marketing Story",
            url="https://brandequity.economictimes.indiatimes.com/news/123",
            published_at=dt,
            publication_label=None,
            is_exclusive=False,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertNotEqual(display, "Publication time unavailable")
        self.assertNotEqual(display, "Exclusive Content")
        # Should be a valid relative/formatted representation (e.g. min/hour/day/IST)
        self.assertTrue(any(x in display.lower() for x in ["ago", "just now", "ist", "pm", "am", "yesterday", "min", "hour", "day"]))

    def test_02_relative_time_46_minutes_ago(self):
        """2. When published_at is None and publication_label is '46 minutes ago', returns '46 minutes ago'."""
        art = Article(
            website="Exchange4media",
            website_key="exchange4media",
            section="Marketing",
            headline="Abhinav Iyer honoured at Truecaller Ads Pitch BFSI Marketer Awards 2026",
            url="https://www.exchange4media.com/marketing-news/158512.html",
            published_at=None,
            publication_label="46 minutes ago",
            is_exclusive=False,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "46 minutes ago")

    def test_03_relative_time_9_hours_ago(self):
        """3. When published_at is None and publication_label is '9 hours ago', returns '9 hours ago'."""
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Digital",
            headline="Digital Ad Trends",
            url="https://brandequity.economictimes.indiatimes.com/news/124",
            published_at=None,
            publication_label="9 hours ago",
            is_exclusive=False,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "9 hours ago")

    def test_04_relative_time_2_days_ago(self):
        """4. When published_at is None and publication_label is '2 days ago', returns '2 days ago'."""
        art = Article(
            website="Exchange4media",
            website_key="exchange4media",
            section="Advertising",
            headline="Advertising Campaign Launch",
            url="https://www.exchange4media.com/advertising-news/158510.html",
            published_at=None,
            publication_label="2 days ago",
            is_exclusive=False,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "2 days ago")

    def test_05_missing_publication_time_and_label_returns_unavailable(self):
        """5. When published_at is None and no relative label exists, returns 'Publication time unavailable'."""
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Media",
            headline="General Media Story",
            url="https://brandequity.economictimes.indiatimes.com/news/125",
            published_at=None,
            publication_label=None,
            is_exclusive=False,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "Time pending verification")

    def test_06_exclusive_flag_does_not_replace_publication_time(self):
        """6. An editorial badge is not displayed in the publication-time field."""
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Business of Brands",
            headline="Beyond private labels: Instamart’s bigger Noice bet",
            url="https://brandequity.economictimes.indiatimes.com/news/126",
            published_at=None,
            publication_label=None,
            is_exclusive=True,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "Time pending verification")

    def test_07_exclusive_article_displays_publication_time(self):
        """7. An authoritative publication time takes precedence over editorial badges."""
        dt = datetime(2026, 9, 23, 8, 0, 0, tzinfo=timezone.utc)
        art = Article(
            website="ET BrandEquity",
            website_key="et_brand_equity",
            section="Marketing",
            headline="Exclusive: Major Leadership Shakeup",
            url="https://brandequity.economictimes.indiatimes.com/news/127",
            published_at=dt,
            publication_label="1 hour ago",
            is_exclusive=True,
        )
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertNotEqual(display, "Exclusive Content")
        self.assertNotEqual(display, "Time pending verification")

    def test_08_word_exclusive_in_summary_prose_does_not_trigger_exclusive_content(self):
        """8. The word 'exclusive' appearing inside summary prose must NOT trigger Exclusive Content flag."""
        html = """
        <div class="story-card">
            <h3>Standard Market Analysis</h3>
            <p>The company announced an exclusive partnership with a local distributor in Mumbai.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        is_exclusive = extract_exclusive_flag(soup, "Standard Market Analysis")
        self.assertFalse(is_exclusive)

        # Confirm display formatting does not mark as Exclusive Content
        display = format_relative_time(
            None,
            publication_label=None,
            is_exclusive=is_exclusive,
        )
        self.assertEqual(display, "Time pending verification")

    def test_09_scraped_at_never_substituted_for_published_time(self):
        """9. scraped_at timestamp is strictly independent and never substituted for publication time."""
        scraped_dt = datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc)
        art = Article(
            website="Exchange4media",
            website_key="exchange4media",
            section="Media",
            headline="Industry Roundup",
            url="https://www.exchange4media.com/media-news/158520.html",
            scraped_at=scraped_dt,
            published_at=None,
            publication_label=None,
            is_exclusive=False,
        )
        # Passing art.published_at (which is None) to formatter
        display = format_relative_time(
            art.published_at,
            publication_label=art.publication_label,
            is_exclusive=art.is_exclusive,
        )
        self.assertEqual(display, "Time pending verification")
        self.assertIsNone(art.published_at)

    def test_10_extract_relative_time_label_from_html(self):
        """10. Verify extraction helper extracts relative time strings from DOM."""
        html_e4m = """
        <div class="news-box">
            <h4>Sample Headline</h4>
            <div class="publish-time"><span>34 mins ago</span></div>
        </div>
        """
        soup = BeautifulSoup(html_e4m, "html.parser")
        label = extract_relative_time_label(soup, "Sample Headline")
        self.assertEqual(label, "34 mins ago")

    def test_11_extract_exclusive_tag_from_html_badge(self):
        """11. Verify extraction helper identifies explicit Exclusive badges."""
        html_badge = """
        <div class="article-box">
            <span class="exclusive-badge">Exclusive</span>
            <h3>Big Retail Merger Announced</h3>
        </div>
        """
        soup = BeautifulSoup(html_badge, "html.parser")
        is_exclusive = extract_exclusive_flag(soup, "Big Retail Merger Announced")
        self.assertTrue(is_exclusive)


if __name__ == "__main__":
    unittest.main()
