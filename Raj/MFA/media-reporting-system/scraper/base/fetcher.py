"""
Media Reporting System - Page Fetcher
Fetches HTML pages using Requests with robots.txt safety check and optional Playwright fallback.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger("media-scraper")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    "MediaReportingSystem/0.1"
)

REQUEST_TIMEOUT = 20


class PageFetcher:
    """Fetch HTML with requests and optionally fall back to Playwright."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9,en-US;q=0.8",
                "Cache-Control": "max-age=0",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self._robots_cache: dict[str, RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        """
        Check robots.txt when available.
        This is a safety check. If robots.txt cannot be parsed or read,
        allows fetch with a logged warning.
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        if robots_url in self._robots_cache:
            rp = self._robots_cache[robots_url]
            return rp.can_fetch(self.user_agent, url)

        rp = RobotFileParser()
        rp.set_url(robots_url)

        try:
            response = self.session.get(
                robots_url,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                self._robots_cache[robots_url] = rp
                allowed = rp.can_fetch(self.user_agent, url)
                if not allowed:
                    logger.warning("robots.txt disallows fetching: %s", url)
                return allowed

            logger.info("Robots.txt returned status %s for %s", response.status_code, robots_url)
            rp.parse(["User-agent: *", "Disallow:"])
            self._robots_cache[robots_url] = rp
            return True
        except Exception as exc:
            logger.info("Robots.txt check skipped for %s (%s)", robots_url, exc)
            rp.parse(["User-agent: *", "Disallow:"])
            self._robots_cache[robots_url] = rp
            return True

    def fetch_requests(self, url: str) -> Optional[str]:
        if not self.can_fetch(url):
            logger.warning("Fetching blocked by robots.txt policy: %s", url)
            return None

        try:
            response = self.session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                logger.warning("Not an HTML page: %s (%s)", url, content_type)
                return None

            return response.text
        except requests.Timeout:
            logger.error("Connection timed out fetching %s", url)
            return None
        except requests.RequestException as exc:
            logger.error("HTTP fetch failed for %s: %s", url, exc)
            return None

    def fetch_playwright(self, url: str) -> Optional[str]:
        """
        Optional browser fallback for dynamic content if requests is blocked or empty.
        Playwright is strictly optional and not required.
        """
        if not self.can_fetch(url):
            return None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.info("Playwright is not installed. Skipping browser fallback.")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=self.user_agent)
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=REQUEST_TIMEOUT * 1000,
                )
                page.wait_for_timeout(1500)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            logger.warning("Playwright fetch failed for %s: %s", url, exc)
            return None

    def fetch(self, url: str, browser_fallback: bool = False) -> Optional[str]:
        """Fetch URL content via Requests, falling back to Playwright only if requested."""
        html = self.fetch_requests(url)
        if html:
            return html

        if browser_fallback:
            logger.info("Attempting browser fallback fetch for %s", url)
            return self.fetch_playwright(url)

        return None
