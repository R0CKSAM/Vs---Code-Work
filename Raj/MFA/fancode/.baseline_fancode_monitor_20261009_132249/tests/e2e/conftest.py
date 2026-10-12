"""
conftest.py – Shared Playwright fixtures for all E2E tests.

NOTE: pytest-playwright already registers --headed, --base-url, --browser,
      --slowmo, and provides browser/context/page fixtures.
      This conftest only adds project-specific configuration on top.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
from playwright.sync_api import Page

# ── Make the project root importable ─────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings  # noqa: E402

# ── Ensure output directories exist ──────────────────────────────────────────
SCREENSHOT_DIR = ROOT / settings.SCREENSHOT_DIR
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = ROOT / settings.LOG_DIR
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Custom CLI options (only options NOT already provided by pytest-playwright)
# --headed    → provided by pytest-playwright
# --base-url  → provided by pytest-base-url
# --browser   → provided by pytest-playwright
# --slowmo    → provided by pytest-playwright
# ──────────────────────────────────────────────────────────────────────────────

def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI options that pytest-playwright does NOT provide."""
    parser.addoption(
        "--browser-timeout",
        action="store",
        default=str(settings.BROWSER_TIMEOUT),
        help=f"Default navigation timeout in ms (default: {settings.BROWSER_TIMEOUT}).",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_timeout(request: pytest.FixtureRequest) -> int:
    """Navigation timeout in milliseconds (from --browser-timeout)."""
    return int(request.config.getoption("--browser-timeout"))


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extend pytest-playwright's launch args with project defaults.
    Adds --no-sandbox for CI compatibility.
    """
    return {
        **browser_type_launch_args,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }


@pytest.fixture(scope="function")
def browser_context_args(
    browser_context_args: Dict[str, Any],
    browser_timeout: int,
) -> Dict[str, Any]:
    """
    Extend pytest-playwright's context args with project viewport,
    locale, timezone and user-agent.
    """
    return {
        **browser_context_args,
        "viewport": {
            "width": settings.BROWSER_VIEWPORT_WIDTH,
            "height": settings.BROWSER_VIEWPORT_HEIGHT,
        },
        "locale": "en-US",
        "timezone_id": "UTC",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Screenshot on failure
# ──────────────────────────────────────────────────────────────────────────────

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    """Attach the call-phase report to the node so screenshot_on_failure can read it."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(scope="function", autouse=True)
def screenshot_on_failure(
    request: pytest.FixtureRequest,
    page: Page,
) -> Generator[None, None, None]:
    """Auto-capture a screenshot to screenshots/ on any test failure."""
    yield

    rep = getattr(request.node, "rep_call", None)
    if rep and rep.failed:
        safe_name = request.node.name.replace("/", "_").replace("\\", "_")
        screenshot_path = SCREENSHOT_DIR / f"{safe_name}.png"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"\n  Screenshot saved: {screenshot_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n  Could not capture screenshot: {exc}")
