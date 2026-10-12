"""
test_discovery.py – Playwright E2E tests for FanCode Discovery Engine.

Covers the minimum required automated tests:
TEST 1: Homepage discovery works.
TEST 2: Relevant internal FanCode links can be discovered.
TEST 3: Discovered links stay within the FanCode domain.
TEST 4: URL normalization removes true duplicates.
TEST 5: Page classification produces valid classifications.
TEST 6: Network monitoring captures relevant requests without crashing.
TEST 7: Discovery terminates within configured limits (e.g. max_pages=2).
TEST 8: Discovery does not enter an infinite crawl.
TEST 9: Discovery handles a page with no relevant links.
TEST 10: Discovery handles navigation/content changes gracefully.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Browser, Page

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.scraper.discovery.crawler import FanCodeCrawler
from app.scraper.discovery.models import PageType
from app.scraper.discovery.network_monitor import NetworkMonitor
from app.scraper.discovery.page_classifier import classify_page, classify_url
from app.scraper.discovery.url_normalizer import (
    are_duplicates,
    deduplicate,
    is_internal,
    normalize,
)


class TestFanCodeDiscoveryE2E:
    """Live Playwright E2E test suite for Discovery Engine."""

    # TEST 1: Homepage discovery works
    def test_homepage_discovery_works(self, page: Page) -> None:
        """Verify we can navigate to homepage and extract core page metadata."""
        resp = page.goto(
            settings.BASE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        assert resp is not None
        assert resp.status in range(200, 400)
        assert page.title() != ""
        classification = classify_page(page.url, page.title())
        assert classification in [PageType.HOME, PageType.UNKNOWN]

    # TEST 2: Relevant internal FanCode links can be discovered
    def test_internal_links_discovered(self, page: Page) -> None:
        """Extract links from homepage and verify at least some valid links exist."""
        page.goto(
            settings.BASE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        anchors = page.locator("a[href]").all()
        assert len(anchors) > 0, "Expected at least one anchor tag on FanCode homepage"

        discovered_internal = []
        for a in anchors[:40]:
            href = a.get_attribute("href")
            if href:
                norm = normalize(href, page.url)
                if norm and is_internal(norm):
                    discovered_internal.append(norm)

        assert len(discovered_internal) > 0, "Expected to find at least one internal FanCode link"

    # TEST 3: Discovered links stay within the FanCode domain
    def test_discovered_links_stay_within_fancode_domain(self, page: Page) -> None:
        page.goto(
            settings.BASE_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        anchors = page.locator("a[href]").all()
        for a in anchors[:30]:
            href = a.get_attribute("href")
            if href:
                norm = normalize(href, page.url)
                if norm:
                    assert is_internal(norm) is True, f"Non-internal URL escaped filter: {norm}"

    # TEST 4: URL normalization removes true duplicates
    def test_url_normalization_removes_true_duplicates(self) -> None:
        raw_urls = [
            "https://www.fancode.com/cricket",
            "https://www.fancode.com/cricket/",
            "https://www.fancode.com/cricket?utm_source=twitter",
            "https://www.fancode.com/cricket#stats",
        ]
        normalized_set = {normalize(u, settings.BASE_URL) for u in raw_urls}
        assert len(normalized_set) == 1
        assert "https://www.fancode.com/cricket" in normalized_set

    # TEST 5: Page classification produces valid classifications
    def test_page_classification_produces_valid_classifications(self) -> None:
        valid_types = PageType.values()
        cases = [
            ("https://www.fancode.com", "FanCode: Watch Live"),
            ("https://www.fancode.com/schedule", "Upcoming Match Schedule"),
            ("https://www.fancode.com/live", "Watch Live Cricket"),
            ("https://www.fancode.com/cricket", "Cricket Tournaments"),
            ("https://www.fancode.com/matches/1234", "Team A vs Team B Live"),
            ("https://www.fancode.com/video/best-sixes", "Match Highlights"),
        ]
        for url, title in cases:
            c = classify_page(url, title)
            assert c.value in valid_types
            assert c != PageType.UNKNOWN

    # TEST 6: Network monitoring captures relevant requests without crashing
    def test_network_monitoring_captures_requests(self, page: Page) -> None:
        monitor = NetworkMonitor(page, page_url=settings.BASE_URL)
        monitor.attach()
        try:
            page.goto(
                settings.BASE_URL,
                wait_until="domcontentloaded",
                timeout=settings.BROWSER_TIMEOUT,
            )
            events = monitor.get_events()
            assert isinstance(events, list)
            # Normal page navigation triggers at least a document request or fetch
            assert len(events) >= 1
            for e in events:
                assert e.url.startswith("http")
                assert e.method != ""
        finally:
            monitor.detach()

    # TEST 7: Discovery terminates within configured limits
    def test_discovery_terminates_within_configured_limits(self, browser: Browser) -> None:
        crawler = FanCodeCrawler(
            browser=browser,
            max_pages=2,
            max_depth=1,
            max_links_per_page=5,
            timeout_seconds=30,
            delay_seconds=0.1,
            seed_url=settings.BASE_URL,
        )
        result = crawler.run()
        assert result.page_count <= 2
        assert result.page_count >= 1

    # TEST 8: Discovery does not enter an infinite crawl
    def test_discovery_does_not_infinite_crawl(self, browser: Browser) -> None:
        crawler = FanCodeCrawler(
            browser=browser,
            max_pages=1,
            max_depth=0,
            timeout_seconds=20,
            delay_seconds=0.0,
            seed_url=settings.BASE_URL,
        )
        result = crawler.run()
        assert result.page_count == 1

    # TEST 9: Discovery handles a page with no relevant links
    def test_discovery_handles_page_with_no_links(self, browser: Browser) -> None:
        # Use data URL HTML containing no anchor tags
        context = browser.new_context()
        page = context.new_page()
        try:
            page.set_content("<html><head><title>Empty Page</title></head><body>No links here</body></html>")
            crawler = FanCodeCrawler(
                browser=browser,
                max_pages=1,
                max_depth=1,
            )
            links = crawler._extract_internal_links(page, "https://www.fancode.com/empty")
            assert links == []
        finally:
            page.close()
            context.close()

    # TEST 10: Discovery handles navigation/content changes gracefully
    def test_discovery_handles_navigation_gracefully(self, browser: Browser) -> None:
        context = browser.new_context()
        crawler = FanCodeCrawler(
            browser=browser,
            max_pages=1,
            max_depth=1,
            seed_url="https://www.fancode.com/non-existent-page-404-test",
        )
        # Should not raise uncaught exception
        result = crawler.run()
        assert result.page_count == 1
        page_res = result.pages[0]
        assert page_res.url == "https://www.fancode.com/non-existent-page-404-test"
        context.close()
