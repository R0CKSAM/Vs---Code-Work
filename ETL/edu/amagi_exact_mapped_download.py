from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"

# Keep this script beside the profile folder created during your manual login.
PROFILE_FOLDER = Path("amagi_browser_profile").resolve()
DOWNLOAD_FOLDER = Path("downloads").resolve()

# These are the exact controls captured with Playwright Inspector.
CHANNEL_DROPDOWN_SELECTOR = ".sv2h-sv2h221"
DOWNLOAD_BUTTON_SELECTOR = ".sv2h-sv2h200"
CHANNEL_NAME = "Samsung TV Plus - IN"


def first_visible(locator: Locator) -> Locator:
    """Return the first currently visible match."""
    count = locator.count()

    for index in range(count):
        candidate = locator.nth(index)
        if candidate.is_visible():
            return candidate

    raise RuntimeError("The mapped element exists but none of its matches are visible.")


def open_dashboard(page: Page) -> None:
    page.goto(
        PORTAL_URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_timeout(4_000)

    if "login.amagi.tv" in page.url.lower():
        print("Your saved login session has expired.")
        print("Log in manually in the opened browser.")
        input(
            "After the Concurrency dashboard is fully visible, "
            "return here and press Enter... "
        )

        page.goto(
            PORTAL_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(4_000)


def select_yesterday(page: Page) -> None:
    yesterday = first_visible(
        page.get_by_text("Yesterday", exact=True)
    )

    yesterday.scroll_into_view_if_needed()
    yesterday.click(timeout=30_000)
    print('Selected "Yesterday".')

    # Allow the dashboard data to refresh.
    page.wait_for_timeout(7_000)


def select_channel(page: Page) -> None:
    dropdown = first_visible(
        page.locator(CHANNEL_DROPDOWN_SELECTOR)
    )

    dropdown.scroll_into_view_if_needed()
    dropdown.click(timeout=30_000)
    page.wait_for_timeout(1_500)

    channel_matches = page.get_by_text(CHANNEL_NAME, exact=True)

    # Your recorder selected nth(1). Prefer that match when it exists,
    # otherwise use the first visible matching option.
    if channel_matches.count() > 1 and channel_matches.nth(1).is_visible():
        channel_option = channel_matches.nth(1)
    else:
        channel_option = first_visible(channel_matches)

    channel_option.scroll_into_view_if_needed()
    channel_option.click(timeout=30_000)
    print(f'Selected channel "{CHANNEL_NAME}".')

    # Allow the channel data to refresh.
    page.wait_for_timeout(7_000)


def download_report(page: Page) -> Path:
    download_button = first_visible(
        page.locator(DOWNLOAD_BUTTON_SELECTOR)
    )

    download_button.scroll_into_view_if_needed()

    print("Starting report download...")

    with page.expect_download(timeout=90_000) as download_info:
        download_button.click(timeout=30_000)

    download = download_info.value

    original_name = Path(download.suggested_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if original_name.suffix:
        output_name = (
            f"{original_name.stem}_yesterday_{timestamp}"
            f"{original_name.suffix}"
        )
    else:
        output_name = f"amagi_yesterday_{timestamp}.csv"

    output_path = DOWNLOAD_FOLDER / output_name

    # This waits for completion and saves the file in our downloads folder.
    download.save_as(str(output_path))

    print(f"Downloaded successfully: {output_path}")
    return output_path


def main() -> int:
    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_FOLDER),
                channel="msedge",
                headless=False,
                viewport={"width": 1440, "height": 900},
                accept_downloads=True,
            )
        except PlaywrightError as error:
            print("Could not open the saved browser profile.")
            print(
                "Close every Edge window opened by an earlier automation "
                "script, then run this script again."
            )
            print(f"Details: {error}")
            return 1

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)

        try:
            open_dashboard(page)
            select_yesterday(page)
            select_channel(page)
            output_path = download_report(page)

            page.screenshot(
                path="amagi_download_success.png",
                full_page=True,
            )

            print()
            print("Finished.")
            print(f"File location: {output_path}")
            return 0

        except PlaywrightTimeoutError as error:
            print()
            print(f"A mapped control timed out: {error}")
            page.screenshot(
                path="amagi_timeout_debug.png",
                full_page=True,
            )
            print("Debug screenshot saved as amagi_timeout_debug.png.")
            input("Press Enter to close the browser... ")
            return 1

        except Exception as error:
            print()
            print(f"Automation failed: {error}")
            page.screenshot(
                path="amagi_error_debug.png",
                full_page=True,
            )
            print("Debug screenshot saved as amagi_error_debug.png.")
            input("Press Enter to close the browser... ")
            return 1

        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
