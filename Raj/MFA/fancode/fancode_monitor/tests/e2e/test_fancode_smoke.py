"""
test_fancode_smoke.py – Phase 0 smoke tests for FanCode Monitor.

Tests
-----
TestFanCodeSmokeBasic
    - test_page_loads_successfully          – HTTP 2xx/3xx response
    - test_page_has_meaningful_title        – <title> non-empty and relevant
    - test_page_has_visible_fancode_content – URL/body/attribute identity check
    - test_browser_closes_cleanly           – page lifecycle sanity
test_settings_loaded_correctly              – settings unit sanity (no browser)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page

# ── Ensure app is importable ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

FANCODE_KEYWORDS = re.compile(r"fancode", re.IGNORECASE)
HTTP_SUCCESS_RANGE = range(200, 400)
TARGET_URL = settings.BASE_URL


# ──────────────────────────────────────────────────────────────────────────────
# Smoke tests
# ──────────────────────────────────────────────────────────────────────────────

class TestFanCodeSmokeBasic:
    """
    Lightweight smoke tests against the live FanCode homepage.
    No scraping, no form submission, no gated content.
    """

    def test_page_loads_successfully(self, page: Page) -> None:
        """Navigate to FanCode and verify HTTP 2xx/3xx response."""
        response = page.goto(
            TARGET_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )

        assert response is not None, (
            "page.goto() returned None – navigation failed completely."
        )
        assert response.status in HTTP_SUCCESS_RANGE, (
            f"Expected HTTP 2xx/3xx, got {response.status} for {TARGET_URL}"
        )

    def test_page_has_meaningful_title(self, page: Page) -> None:
        """
        <title> must be non-empty and contain a sports/FanCode keyword.
        Pattern is intentionally broad to survive A/B title experiments.
        """
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)

        title = page.title()
        assert title and title.strip(), (
            "Page title is empty – page may not have loaded correctly."
        )

        positive = re.compile(
            r"fancode|sports?|cricket|football|fantasy|stream|live",
            re.IGNORECASE,
        )
        assert positive.search(title), (
            f"Title '{title}' does not appear to belong to a sports/FanCode platform."
        )

    def test_page_has_visible_fancode_content(self, page: Page) -> None:
        """
        At least ONE must be true after load:
          (a) URL contains 'fancode.com'   – domain check
          (b) Body text contains 'fancode' – text check
          (c) An element attribute mentions 'fancode' – asset/logo check
        """
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)

        # (a) URL domain
        if "fancode.com" in page.url:
            return

        # (b) Body text
        body_text = page.inner_text("body") if page.locator("body").count() else ""
        if FANCODE_KEYWORDS.search(body_text):
            return

        # (c) Attribute search
        attr_loc = page.locator(
            "[alt*='fancode' i], [aria-label*='fancode' i], "
            "[src*='fancode' i], [href*='fancode' i]"
        )
        if attr_loc.count() > 0:
            return

        pytest.fail(
            f"No FanCode-identifying content found.\n"
            f"  URL  : {page.url}\n"
            f"  Title: {page.title()}\n"
            f"  Body (first 500): {body_text[:500]}"
        )

    def test_browser_closes_cleanly(self, page: Page) -> None:
        """Verify navigation + teardown path raises no exceptions."""
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)
        assert not page.is_closed(), "Page was unexpectedly closed before teardown."


# ──────────────────────────────────────────────────────────────────────────────
# Settings sanity (no browser required)
# ──────────────────────────────────────────────────────────────────────────────

def test_settings_loaded_correctly() -> None:
    """Settings object loads without errors and has sensible defaults."""
    assert settings.BASE_URL.startswith("https://"), (
        f"BASE_URL should start with https://, got: {settings.BASE_URL}"
    )
    assert settings.BROWSER_TIMEOUT > 0, "BROWSER_TIMEOUT must be positive"
    assert settings.BROWSER_VIEWPORT_WIDTH > 0
    assert settings.BROWSER_VIEWPORT_HEIGHT > 0
    assert isinstance(settings.BROWSER_HEADLESS, bool)
