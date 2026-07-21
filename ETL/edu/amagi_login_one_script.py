from pathlib import Path
import re

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

# ============================================================
# ADD YOUR LOGIN DETAILS LATER
# ============================================================
USERNAME = ""
PASSWORD = ""

PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"

# This folder stores cookies/session so you may not need to log in every time.
PROFILE_FOLDER = Path("amagi_browser_profile").resolve()


def find_visible(page, selectors):
    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = min(locator.count(), 10)
        except Exception:
            continue

        for index in range(count):
            element = locator.nth(index)

            try:
                if element.is_visible():
                    return element
            except Exception:
                pass

    return None


def find_submit_button(page):
    button_names = [
        r"sign\s*in",
        r"log\s*in",
        r"login",
        r"continue",
        r"next",
        r"submit",
    ]

    for name in button_names:
        locator = page.get_by_role(
            "button",
            name=re.compile(name, re.IGNORECASE),
        )

        try:
            count = min(locator.count(), 10)
        except Exception:
            continue

        for index in range(count):
            button = locator.nth(index)

            try:
                if button.is_visible() and button.is_enabled():
                    return button
            except Exception:
                pass

    return find_visible(
        page,
        [
            'button[type="submit"]',
            'input[type="submit"]',
        ],
    )


def login(page):
    if not USERNAME or not PASSWORD:
        print("USERNAME and PASSWORD are empty.")
        print("Enter them at the top of this script or log in manually.")
        return

    username_input = find_visible(
        page,
        [
            'input[autocomplete="username"]',
            'input[type="email"]',
            'input[name*="email" i]',
            'input[id*="email" i]',
            'input[name*="user" i]',
            'input[id*="user" i]',
            'input[type="text"]',
        ],
    )

    if username_input:
        username_input.fill(USERNAME)
    else:
        print("Username field was not found automatically.")
        return

    password_input = find_visible(
        page,
        [
            'input[autocomplete="current-password"]',
            'input[type="password"]',
        ],
    )

    # Some login pages ask for the username first.
    if not password_input:
        next_button = find_submit_button(page)

        if next_button:
            next_button.click()
            page.wait_for_timeout(2000)

            password_input = find_visible(
                page,
                [
                    'input[autocomplete="current-password"]',
                    'input[type="password"]',
                ],
            )

    if not password_input:
        print("Password field was not found automatically.")
        print("Complete the login manually in the browser.")
        return

    password_input.fill(PASSWORD)

    submit_button = find_submit_button(page)

    if submit_button:
        submit_button.click()
        print("Login submitted.")
    else:
        print("Submit button was not found.")
        print("Click it manually in the browser.")


def main():
    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_FOLDER),
            headless=False,
            viewport={"width": 1440, "height": 900},
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        try:
            page.goto(
                PORTAL_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except PlaywrightTimeoutError:
            print("The page is still loading. Continue in the browser.")

        page.wait_for_timeout(2000)
        login(page)

        print()
        print("Complete any SSO, OTP, MFA, or CAPTCHA manually.")
        print("Keep the browser open while you use the dashboard.")
        input("Press Enter here when you want to close the browser... ")

        try:
            page.screenshot(
                path="amagi_dashboard.png",
                full_page=True,
            )
            print("Screenshot saved as amagi_dashboard.png")
        except Exception as error:
            print(f"Screenshot could not be saved: {error}")

        browser.close()


if __name__ == "__main__":
    main()
