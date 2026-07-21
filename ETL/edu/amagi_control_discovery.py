"""List usable Amagi dashboard controls without pausing the web application.

Unlike Playwright Inspector's ``page.pause()``, this keeps the React dashboard
running while a user completes login and waits for data to load.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent
PORTAL_URL = "https://indiatvfast.now3.amagi.tv/partner/analytics/concurrency"
PROFILE_FOLDER = HERE / "amagi_browser_profile"
# Chromium and Edge do not safely share one profile directory.  A fallback
# needs its own profile or Chromium can try to downgrade Edge cache files.
FALLBACK_PROFILE_FOLDER = HERE / "amagi_playwright_profile"
DIAGNOSTICS_FOLDER = HERE / "diagnostics"


def launch_context(playwright):
    options = {
        "user_data_dir": str(PROFILE_FOLDER),
        "headless": False,
        "viewport": {"width": 1440, "height": 900},
        "accept_downloads": True,
    }
    try:
        return playwright.chromium.launch_persistent_context(channel="msedge", **options)
    except PlaywrightError as exc:
        print(f"Edge profile could not start: {exc}")
        print("Using a separate Playwright Chromium profile; complete SSO once in that browser.")
        fallback_options = {**options, "user_data_dir": str(FALLBACK_PROFILE_FOLDER)}
        return playwright.chromium.launch_persistent_context(**fallback_options)


def collect_controls(page) -> list[dict[str, str | bool]]:
    """Capture semantic and custom clickable controls without generated selectors."""
    controls: list[dict[str, str | bool]] = []
    seen: set[tuple[str, str, str]] = set()
    for frame_index, frame in enumerate(page.frames):
        try:
            # Amagi's dashboard uses clickable divs instead of native controls.
            # Browser-side inspection also reaches controls in open shadow roots.
            items = frame.evaluate(
                """() => {
                  const output = [];
                  const visited = new Set();
                  const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
                  const visible = node => {
                    const style = getComputedStyle(node);
                    const box = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden'
                      && Number(style.opacity || 1) > 0 && box.width > 0 && box.height > 0;
                  };
                  const visit = root => {
                    root.querySelectorAll('*').forEach(node => {
                      if (visited.has(node)) return;
                      visited.add(node);
                      if (node.shadowRoot) visit(node.shadowRoot);
                      if (!visible(node)) return;
                      const tag = node.tagName.toLowerCase();
                      const role = clean(node.getAttribute('role'));
                      const ariaLabel = clean(node.getAttribute('aria-label'));
                      const title = clean(node.getAttribute('title'));
                      const tabIndex = node.tabIndex;
                      const cursor = getComputedStyle(node).cursor;
                      const native = ['button', 'input', 'select', 'textarea', 'a'].includes(tag);
                      const interactive = native || Boolean(role) || Boolean(ariaLabel) || Boolean(title)
                        || tabIndex >= 0 || cursor === 'pointer';
                      if (!interactive) return;
                      const text = clean(node.innerText).slice(0, 300);
                      const name = ariaLabel || title || text || clean(node.getAttribute('name'))
                        || clean(node.getAttribute('placeholder'));
                      if (!name) return;
                      output.push({
                        tag, role, name, text, aria_label: ariaLabel, title,
                        type: clean(node.getAttribute('type')),
                        placeholder: clean(node.getAttribute('placeholder')),
                        test_id: clean(node.getAttribute('data-testid')),
                        id: clean(node.id),
                        class_hint: clean(node.className).slice(0, 180),
                        enabled: !node.hasAttribute('disabled') && node.getAttribute('aria-disabled') !== 'true',
                      });
                    });
                  };
                  visit(document);
                  return output.slice(0, 750);
                }"""
            )
        except PlaywrightError:
            continue
        for item in items:
            identity = (str(item["tag"]), str(item["role"]), str(item["name"]))
            if identity in seen:
                continue
            seen.add(identity)
            item["frame"] = "main" if frame_index == 0 else f"frame_{frame_index}"
            controls.append(item)
    return controls


def wait_for_chart_data(page, timeout_seconds: int = 45) -> bool:
    """Wait for a Recharts line path instead of assuming a fixed sleep is enough."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            paths = page.locator("svg path[d]")
            for index in range(min(paths.count(), 80)):
                path_data = paths.nth(index).get_attribute("d") or ""
                if len(path_data) > 80:
                    return True
        except PlaywrightError:
            pass
        page.wait_for_timeout(1_000)
    return False


def install_pointer_tracker(page) -> None:
    """Remember the last cursor position so an icon-only control can be identified."""
    page.evaluate(
        """() => {
          if (window.__amagiPointerTrackerInstalled) return;
          window.__amagiPointerTrackerInstalled = true;
          document.addEventListener('mousemove', event => {
            window.__amagiLastPointer = {x: event.clientX, y: event.clientY};
          }, {passive: true});
        }"""
    )


def wait_for_stable_page(page, timeout_seconds: int = 30) -> bool:
    """SSO can navigate after the user presses Enter; wait for that navigation to settle."""
    deadline = time.monotonic() + timeout_seconds
    previous_url = ""
    stable_checks = 0
    while time.monotonic() < deadline:
        try:
            ready_state = page.evaluate("document.readyState")
            current_url = page.url
            if ready_state in {"interactive", "complete"} and current_url == previous_url:
                stable_checks += 1
                if stable_checks >= 2:
                    return True
            else:
                stable_checks = 0
            previous_url = current_url
        except PlaywrightError:
            stable_checks = 0
        page.wait_for_timeout(1_000)
    return False


def hovered_control(page) -> dict[str, object] | None:
    """Describe the element under the last browser cursor position and its parents."""
    try:
        return page.evaluate(
            """() => {
              const point = window.__amagiLastPointer;
              if (!point) return null;
              const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
              const node = document.elementFromPoint(point.x, point.y);
              if (!node) return null;
              const describe = element => {
                const box = element.getBoundingClientRect();
                return {
                  tag: element.tagName.toLowerCase(),
                  text: clean(element.innerText).slice(0, 300),
                  aria_label: clean(element.getAttribute('aria-label')),
                  title: clean(element.getAttribute('title')),
                  role: clean(element.getAttribute('role')),
                  test_id: clean(element.getAttribute('data-testid')),
                  id: clean(element.id),
                  class_hint: clean(element.className).slice(0, 220),
                  rect: {x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width), height: Math.round(box.height)},
                };
              };
              const ancestors = [];
              let current = node;
              for (let index = 0; current && index < 7; index += 1, current = current.parentElement) {
                ancestors.push(describe(current));
              }
              return {point, ancestors};
            }"""
        )
    except PlaywrightError:
        return None


def main() -> int:
    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    FALLBACK_PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS_FOLDER.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with sync_playwright() as playwright:
        context = launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            try:
                page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
            except PlaywrightTimeoutError:
                print("The dashboard shell is open and may still be loading.")

            print("\nComplete Amagi SSO manually if asked, then wait for the dashboard to finish loading.")
            input("When the page is ready, press Enter to capture its visible controls... ")
            if not wait_for_stable_page(page):
                print("The page did not fully settle after login; continuing with a best-effort capture.")
            try:
                install_pointer_tracker(page)
            except PlaywrightError:
                # A late SSO redirect can still win this race.  The capture is
                # useful without hover details, so do not discard it.
                print("The page navigated while installing hover capture; hover details may be unavailable this run.")
            chart_loaded = wait_for_chart_data(page)
            print("Chart data detected." if chart_loaded else "No chart line detected after 45 seconds; saving a diagnostic capture anyway.")

            controls = collect_controls(page)
            print("\nOptional: move the mouse over the export/download icon in the browser, do not click it, then press Enter here.")
            input("Press Enter to record the hovered control, or press Enter without hovering to skip... ")
            hover = hovered_control(page)
            output = DIAGNOSTICS_FOLDER / f"amagi_controls_{stamp}.json"
            output.write_text(
                json.dumps(
                    {
                        "url": page.url,
                        "captured_at": datetime.now().isoformat(),
                        "chart_data_detected": chart_loaded,
                        "hovered_control": hover,
                        "controls": controls,
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            screenshot = DIAGNOSTICS_FOLDER / f"amagi_controls_{stamp}.png"
            page.screenshot(path=str(screenshot), full_page=True)

            print(f"\nCaptured {len(controls)} visible controls.")
            print(f"Controls   : {output}")
            print(f"Screenshot : {screenshot}")
            return 0
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
