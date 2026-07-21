"""Validate Amagi portal access before configuring download automation.

This script deliberately never stores a username or password.  It keeps the
browser session in ``amagi_browser_profile`` so that, after one successful
interactive SSO login, later download scripts can reuse the authorised session.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent
PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"
PROFILE_FOLDER = HERE / "amagi_browser_profile"
DIAGNOSTICS_FOLDER = HERE / "diagnostics"


def launch_context(playwright):
    """Prefer Edge but retain Playwright Chromium as a portable fallback."""
    options = {
        "user_data_dir": str(PROFILE_FOLDER),
        "headless": False,
        "viewport": {"width": 1440, "height": 900},
        "accept_downloads": True,
    }
    try:
        return playwright.chromium.launch_persistent_context(channel="msedge", **options)
    except PlaywrightError as exc:
        print(f"Edge could not start ({exc}). Falling back to Playwright Chromium.")
        return playwright.chromium.launch_persistent_context(**options)


def access_status(page) -> tuple[bool, str]:
    """Detect the portal's visible access-denied state without relying on CSS classes."""
    body = page.locator("body").inner_text(timeout=10_000).lower()
    denied_markers = (
        "forbidden",
        "permission to access this resource is denied",
        "access denied",
        "unauthorized",
    )
    if any(marker in body for marker in denied_markers):
        return False, "The signed-in account does not currently have permission for this dashboard."
    if "login.amagi.tv" in page.url.lower():
        return False, "The portal redirected to login; complete SSO and then re-check access."
    return True, "Portal access looks available."


def save_screenshot(page, label: str) -> Path:
    DIAGNOSTICS_FOLDER.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DIAGNOSTICS_FOLDER / f"amagi_{label}_{stamp}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def main() -> int:
    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS_FOLDER.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)
        try:
            try:
                page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
            except PlaywrightTimeoutError:
                # The SPA may keep loading after its shell is usable.
                print("The page is still loading; inspect it in the opened browser.")
            page.wait_for_timeout(4_000)

            allowed, message = access_status(page)
            if not allowed:
                print(f"\nAccess check: {message}")
                print("Log in with the Amagi account that can open this dashboard.")
                input("When the Concurrency dashboard is visible, press Enter here to check again... ")
                try:
                    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(4_000)
                allowed, message = access_status(page)

            screenshot = save_screenshot(page, "access_ok" if allowed else "access_denied")
            print(f"\nAccess check: {message}")
            print(f"Current URL : {page.url}")
            print(f"Screenshot  : {screenshot}")
            if allowed:
                print("\nNext: we can capture the real download action once and turn it into a batch downloader.")
                return 0
            print("\nThis is an Amagi role/tenant permission issue, not a Playwright selector issue.")
            return 2
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
