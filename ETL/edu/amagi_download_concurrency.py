"""Download an Amagi Concurrency report with a persistent authorised session.

The portal uses generated CSS classes, so this script deliberately locates the
chart card by its visible content and clicks its top-right SVG export control.
It defaults to the currently selected channel and Yesterday, making it safe for
the first verification download before batch automation is enabled.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from datetime import datetime
from pathlib import Path

# A PowerShell session can retain PWDEBUG=1 from a prior locator-mapping run.
# Remove it before Playwright starts so this production downloader never opens
# Playwright Inspector or pauses the single-page dashboard.
os.environ.pop("PWDEBUG", None)

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent
PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"
# The successful interactive login was captured in this Playwright Chromium
# profile.  Keeping one engine/profile pair prevents Edge and Chromium from
# presenting different Amagi sessions to the same automation.
PROFILE_FOLDER = HERE / "amagi_playwright_profile"
DOWNLOAD_FOLDER = HERE / "downloads"
DIAGNOSTICS_FOLDER = HERE / "diagnostics"
# Give Amagi's SPA and its report backend a full settling window after a date
# switch. The visible Yesterday button can update before the export payload.
REPORT_SETTLE_SECONDS = 60
YESTERDAY_CHANNEL_GROUPS = (
    "India TV AKA Samsung",
    "India TV Live",
    "India TV Live Samsung",
    "India TV Maha Kumbh",
    "India TV Speed News",
    "India TV Speed News Samsung",
    "India TV Yoga Samsung",
    "IndiaTV AapkiAdalat",
    "IndiaTV Yoga",
)


def launch_context(playwright):
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_FOLDER),
        headless=False,
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
    )


def wait_for_stable_page(page, timeout_seconds: int = 30) -> bool:
    deadline = time.monotonic() + timeout_seconds
    previous_url = ""
    stable_checks = 0
    while time.monotonic() < deadline:
        try:
            ready_state = page.evaluate("document.readyState")
            if ready_state in {"interactive", "complete"} and page.url == previous_url:
                stable_checks += 1
                if stable_checks >= 2:
                    return True
            else:
                stable_checks = 0
            previous_url = page.url
        except PlaywrightError:
            stable_checks = 0
        page.wait_for_timeout(1_000)
    return False


def assert_access(page) -> None:
    # A successful dashboard can retain an earlier toast saying "Forbidden"
    # after SSO refresh.  Real, visible dashboard controls are stronger access
    # evidence than that stale notification text.
    try:
        has_channel_picker = page.locator("[data-testid='select-option']").count() > 0
        has_day_toggle = page.locator("[data-testid^='switch-view']").count() > 0
        if has_channel_picker and has_day_toggle:
            return
    except PlaywrightError:
        pass
    body = page.locator("body").inner_text(timeout=10_000).lower()
    denied = ("forbidden", "permission to access this resource is denied", "access denied")
    if any(marker in body for marker in denied):
        raise RuntimeError("The saved Amagi session is not authorised for Concurrency.")
    if "login.amagi.tv" in page.url.lower():
        raise RuntimeError("The saved Amagi session needs SSO login before downloading.")


def navigate_to_concurrency(page, attempts: int = 4) -> None:
    """Let Amagi's SSO redirects settle before requiring the dashboard route."""
    last_error: PlaywrightError | None = None
    for _ in range(attempts):
        try:
            # ``commit`` returns as soon as the navigation starts.  Waiting for
            # DOMContentLoaded here races with Amagi's post-login redirect.
            page.goto(PORTAL_URL, wait_until="commit", timeout=60_000)
        except PlaywrightError as exc:
            last_error = exc
        page.wait_for_timeout(1_500)
        wait_for_stable_page(page, timeout_seconds=20)
        if "/partner/analytics/concurrency" in page.url.lower():
            return
    detail = f" Last navigation error: {last_error}" if last_error else ""
    raise RuntimeError(f"Amagi did not reach the Concurrency route. Current URL: {page.url}.{detail}")


def open_authorised_dashboard(page) -> None:
    """Wait for an interactive SSO refresh without relying on console input."""
    navigate_to_concurrency(page)
    try:
        assert_access(page)
        return
    except RuntimeError as first_error:
        print(f"Session check: {first_error}")
        print("Log in manually in the opened Chromium window. The script will detect access automatically.")
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                if "/partner/analytics/concurrency" in page.url.lower():
                    assert_access(page)
                    return
            except RuntimeError:
                # A stale Forbidden toast is expected until the authenticated
                # app shell and its real controls have rendered.
                pass
            except PlaywrightError:
                pass
            page.wait_for_timeout(1_000)
        raise RuntimeError("Timed out waiting 5 minutes for authorised Concurrency access after manual SSO.")


def wait_for_dashboard_controls(page, timeout_seconds: int = 90) -> None:
    """Wait for the SPA to render its channel picker before interacting with it."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            assert_access(page)
            picker = page.locator("[data-testid='select-option']")
            if picker.count() and picker.first.is_visible():
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(1_000)
    raise RuntimeError("Amagi Concurrency did not finish rendering its controls within 90 seconds.")


def wait_for_chart_data(page, timeout_seconds: int = 60) -> None:
    """A download should only start after the chosen chart has real series data."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            # The empty-state illustration is also an SVG path.  Restrict the
            # check to Recharts' actual line/area data series so an empty chart
            # can never be mistaken for a loaded report.
            paths = page.locator(
                ".recharts-wrapper path.recharts-line-curve, "
                ".recharts-wrapper path.recharts-area-curve"
            )
            if any(len(paths.nth(index).get_attribute("d") or "") > 80 for index in range(min(paths.count(), 80))):
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(1_000)
    raise RuntimeError("The concurrency chart did not receive data within 60 seconds.")


def first_visible(locator):
    for index in range(locator.count()):
        item = locator.nth(index)
        if item.is_visible():
            return item
    raise RuntimeError("Expected portal control is not visible.")


def dismiss_transient_overlays(page) -> None:
    """Close stale Material-UI popovers before operating the channel picker."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        # The portal can leave a transparent presentation layer above the
        # picker after a selection. Clicking the blank left margin closes it.
        overlay = page.locator("[role='presentation']")
        if any(overlay.nth(index).is_visible() for index in range(overlay.count())):
            page.mouse.click(8, 180)
            page.wait_for_timeout(250)
    except PlaywrightError:
        # The next real selector operation supplies the actionable error.
        pass


def normalize_channel_label(value: str) -> str:
    """Compare portal labels despite harmless spacing and platform suffixes."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def channel_label_matches(actual: str, requested: str) -> bool:
    actual_key = normalize_channel_label(actual)
    requested_key = normalize_channel_label(requested)
    return actual_key == requested_key or actual_key.startswith(requested_key)


def selected_report_matches(actual: str, channel_group: str, platform: str) -> bool:
    """Require the selected display label to contain this exact group/platform pair."""
    expected_prefix = normalize_channel_label(channel_group) + normalize_channel_label(platform)
    return normalize_channel_label(actual).startswith(expected_prefix)


def select_day(page, day: str) -> None:
    label = "Yesterday" if day == "yesterday" else "Today"
    button = first_visible(page.get_by_text(label, exact=True))
    button.click(timeout=30_000)
    print(f"Selected {label}.")


def select_channel(page, channel: str) -> str:
    """Select a requested channel and return the exact label used by the portal."""
    picker = first_visible(page.locator("[data-testid='select-option']"))
    current = " ".join(picker.inner_text().split())
    if normalize_channel_label(current) == normalize_channel_label(channel):
        print(f'Channel already selected: "{channel}".')
        return current
    dismiss_transient_overlays(page)
    picker.click(timeout=30_000)
    page.wait_for_timeout(500)
    exact = page.get_by_text(channel, exact=True)
    try:
        option = first_visible(exact)
    except RuntimeError:
        # Some portal labels add a platform in parentheses. Match only a label
        # prefix so "India TV Live" never resolves to an unrelated channel.
        option = first_visible(
            page.get_by_text(re.compile(rf"^{re.escape(channel)}(?:\s|\(|$)"))
        )
    option.click(timeout=30_000)
    page.wait_for_timeout(500)
    dismiss_transient_overlays(page)
    selected = " ".join(picker.inner_text().split())
    if not channel_label_matches(selected, channel):
        raise RuntimeError(
            f'Portal selected "{selected}" instead of requested channel "{channel}".'
        )
    print(f'Selected channel: "{selected}".')
    return selected


def discover_channel_reports(page, requested_groups: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return every selectable platform row beneath the requested channel groups."""
    picker = first_visible(page.locator("[data-testid='select-option']"))
    dismiss_transient_overlays(page)
    picker.click(timeout=30_000)
    menu = page.locator("#simple-status-filter-popover")
    menu.wait_for(state="visible", timeout=30_000)
    page.wait_for_timeout(300)
    records = menu.evaluate(
        """(root, requested) => {
          const wanted = new Set(requested.map(value => value.replace(/[^a-z0-9]+/gi, '').toLowerCase()));
          return [...root.querySelectorAll('li[role="menuitem"]')]
            .map(item => ({
              group: item.parentElement.firstElementChild?.textContent?.trim() || '',
              platform: item.textContent.trim(),
            }))
            .filter(row => wanted.has(row.group.replace(/[^a-z0-9]+/gi, '').toLowerCase()));
        }""",
        list(requested_groups),
    )
    dismiss_transient_overlays(page)
    reports = sorted(
        {(str(row["group"]), str(row["platform"])) for row in records},
        key=lambda row: (row[0].lower(), row[1].lower()),
    )
    if not reports:
        raise RuntimeError("None of the requested channel groups were found in the Amagi picker.")
    return reports


def select_channel_platform(page, channel_group: str, platform: str) -> str:
    """Select one actual platform report under its channel group."""
    picker = first_visible(page.locator("[data-testid='select-option']"))
    current = " ".join(picker.inner_text().split())
    if selected_report_matches(current, channel_group, platform):
        print(f'Channel already selected: "{current}".')
        return current
    dismiss_transient_overlays(page)
    picker.click(timeout=30_000)
    menu = page.locator("#simple-status-filter-popover")
    menu.wait_for(state="visible", timeout=30_000)
    clicked = menu.evaluate(
        """(root, target) => {
          const normalize = value => String(value || '').replace(/[^a-z0-9]+/gi, '').toLowerCase();
          const groupKey = normalize(target.group);
          const platformKey = normalize(target.platform);
          const item = [...root.querySelectorAll('li[role="menuitem"]')].find(node =>
            normalize(node.parentElement.firstElementChild?.textContent) === groupKey
            && normalize(node.textContent) === platformKey
          );
          if (!item) return false;
          item.click();
          return true;
        }""",
        {"group": channel_group, "platform": platform},
    )
    if not clicked:
        dismiss_transient_overlays(page)
        raise RuntimeError(f'Could not find platform "{platform}" under channel "{channel_group}".')
    for _ in range(20):
        page.wait_for_timeout(500)
        selected = " ".join(picker.inner_text().split())
        if selected_report_matches(selected, channel_group, platform):
            dismiss_transient_overlays(page)
            print(f'Selected channel: "{selected}".')
            return selected
    dismiss_transient_overlays(page)
    raise RuntimeError(
        f'Portal did not confirm channel "{channel_group}" on platform "{platform}".'
    )


def chart_export_point(page) -> tuple[float, float]:
    """Return the export control centre without depending on generated CSS names."""
    target = page.evaluate(
        """() => {
          const label = [...document.querySelectorAll('*')]
            .find(node => node.children.length === 0
              && /Number of viewers/i.test(node.textContent || ''));
          if (!label) return null;
          let card = label;
          while (card && card !== document.body) {
            const box = card.getBoundingClientRect();
            if (box.width > 600 && box.height > 250) break;
            card = card.parentElement;
          }
          if (!card) return null;
          const cardBox = card.getBoundingClientRect();
          // Clicking the SVG itself is reliable across the portal's changing
          // button/div wrappers. It is the small icon at the card's top right.
          const candidates = [...card.querySelectorAll('svg')]
            .map(node => ({node, box: node.getBoundingClientRect()}))
            .filter(({box}) => box.width >= 12 && box.width <= 64
              && box.height >= 12 && box.height <= 64
              && box.left >= cardBox.right - 120 && box.top >= cardBox.top - 4
              && box.top <= cardBox.top + 100);
          if (!candidates.length) return null;
          const best = candidates.sort((a, b) => b.box.left - a.box.left)[0].box;
          return {x: best.left + best.width / 2, y: best.top + best.height / 2};
        }"""
    )
    if not target:
        raise RuntimeError("Could not locate the icon-only export control in the concurrency card.")
    return float(target["x"]), float(target["y"])


def safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return clean[:100] or "selected_channel"


def save_download(page, output_dir: Path, channel: str, day: str) -> Path:
    x, y = chart_export_point(page)
    print(f"Clicking export control at chart position {x:.0f}, {y:.0f}...")
    with page.expect_download(timeout=90_000) as download_info:
        page.mouse.click(x, y)
    download = download_info.value
    suffix = Path(download.suggested_filename).suffix or ".csv"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"amagi_concurrency_{safe_filename(channel)}_{day}_{stamp}{suffix}"
    download.save_as(str(output))
    return output


def wait_then_download(page, output_dir: Path, channel: str, day: str) -> Path:
    """Keep the date switch, report readiness check, and export in one order."""
    select_day(page, day)
    print(
        f"Waiting {REPORT_SETTLE_SECONDS} seconds for the selected "
        f"{day.title()} report to settle before export..."
    )
    page.wait_for_timeout(REPORT_SETTLE_SECONDS * 1_000)
    wait_for_chart_data(page)
    return save_download(page, output_dir.resolve(), channel, day)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one Amagi Concurrency report")
    channel_mode = parser.add_mutually_exclusive_group()
    channel_mode.add_argument(
        "--channel", help="Exact channel label; omit to keep the dashboard selection"
    )
    channel_mode.add_argument(
        "--all-yesterday",
        action="store_true",
        help="Download Yesterday for all configured India TV channels sequentially.",
    )
    parser.add_argument("--day", choices=("yesterday", "today"), default="yesterday")
    parser.add_argument("--out", type=Path, default=DOWNLOAD_FOLDER)
    parser.add_argument(
        "--verify-yesterday",
        action="store_true",
        help="Select Yesterday, save a screenshot, and stop before download.",
    )
    args = parser.parse_args()

    if args.all_yesterday and args.verify_yesterday:
        parser.error("--all-yesterday cannot be combined with --verify-yesterday")
    if args.all_yesterday and args.day != "yesterday":
        parser.error("--all-yesterday is intentionally limited to --day yesterday")

    args.out.mkdir(parents=True, exist_ok=True)
    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS_FOLDER.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            open_authorised_dashboard(page)
            wait_for_dashboard_controls(page)
            if args.all_yesterday:
                completed: list[Path] = []
                unavailable: list[str] = []
                failures: list[str] = []
                reports = discover_channel_reports(page, YESTERDAY_CHANNEL_GROUPS)
                total = len(reports)
                print(f"Discovered {total} requested channel/platform reports.")
                for index, (channel_group, platform) in enumerate(reports, start=1):
                    requested = f"{channel_group} | {platform}"
                    print(f"[{index}/{total}] Processing Yesterday for: {requested}")
                    try:
                        selected = select_channel_platform(page, channel_group, platform)
                        output = wait_then_download(page, args.out, selected, "yesterday")
                        completed.append(output)
                        print(f"[{index}/{total}] Downloaded: {output}")
                    except (PlaywrightError, PlaywrightTimeoutError, RuntimeError) as exc:
                        message = str(exc)
                        dismiss_transient_overlays(page)
                        if message == "The concurrency chart did not receive data within 60 seconds.":
                            unavailable.append(requested)
                            print(f"[{index}/{total}] NO DATA for Yesterday, continuing: {requested}")
                            continue
                        failures.append(f"{requested}: {message}")
                        try:
                            page.screenshot(
                                path=str(
                                    DIAGNOSTICS_FOLDER
                                    / f"amagi_batch_{safe_filename(requested)}_error.png"
                                ),
                                full_page=True,
                            )
                        except PlaywrightError:
                            pass
                        print(f"[{index}/{total}] FAILED, continuing: {requested}: {message}")
                print(f"Batch completed: {len(completed)}/{total} downloaded.")
                print(f"No-data reports for Yesterday: {len(unavailable)}.")
                for report in unavailable:
                    print(f"No data: {report}")
                for failure in failures:
                    print(f"Batch failure: {failure}")
                return 0 if not failures else 2
            if args.channel:
                args.channel = select_channel(page, args.channel)
            else:
                selected = first_visible(page.locator("[data-testid='select-option']"))
                args.channel = " ".join(selected.inner_text().split())
                print(f'Keeping selected channel: "{args.channel}".')
            if args.verify_yesterday:
                # This mode verifies only the date control.  A selected channel
                # can legitimately have no data for Yesterday, so do not make
                # the visual toggle check depend on a non-empty chart.
                select_day(page, args.day)
                page.wait_for_timeout(1_500)
                screenshot = DIAGNOSTICS_FOLDER / "amagi_yesterday_selected.png"
                page.screenshot(path=str(screenshot), full_page=True)
                print(f"Yesterday verification screenshot: {screenshot}")
                print("Verification-only mode complete; no download was started.")
                return 0
            output = wait_then_download(page, args.out, args.channel, args.day)
            page.screenshot(path=str(DIAGNOSTICS_FOLDER / "amagi_download_success.png"), full_page=True)
            print(f"Downloaded successfully: {output}")
            return 0
        except (PlaywrightError, PlaywrightTimeoutError, RuntimeError) as exc:
            try:
                page.screenshot(path=str(DIAGNOSTICS_FOLDER / "amagi_download_error.png"), full_page=True)
            except PlaywrightError:
                pass
            raise SystemExit(f"Download failed: {exc}") from exc
        finally:
            try:
                context.close()
            except PlaywrightError:
                # The user may close the visible browser during an interactive
                # verification run; cleanup should not mask the real result.
                pass


if __name__ == "__main__":
    raise SystemExit(main())
