"""Capture a small, sanitized live-site fixture and screenshot for selector review."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "schedule"
URL = "https://www.fancode.com/schedule"
MATCH_ID = re.compile(r"/matches/[^/?#]+-(\d+)(?:/|$)")


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3_000)
        links = page.locator("a[href*='/matches/']")
        records: list[dict[str, str]] = []
        seen: set[str] = set()
        for index in range(min(links.count(), 100)):
            link = links.nth(index)
            href = urljoin(URL, link.get_attribute("href") or "")
            parsed = urlparse(href)
            if parsed.netloc not in {"www.fancode.com", "fancode.com"} or href in seen:
                continue
            text = " ".join((link.inner_text() or "").split())
            match_id = MATCH_ID.search(parsed.path)
            if not text or not match_id:
                continue
            seen.add(href)
            records.append({"id": match_id.group(1), "title": text[:500], "href": href})
            if len(records) == 5:
                break
        page.screenshot(path=str(FIXTURE_DIR / "live_schedule_20261009.png"), full_page=True)
        browser.close()

    (FIXTURE_DIR / "live_schedule_20261009.json").write_text(
        json.dumps({"source_url": URL, "records": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    cards = "\n".join(
        f'<a href="{escape(record["href"], quote=True)}">{escape(record["title"])}</a>'
        for record in records
    )
    (FIXTURE_DIR / "live_schedule_20261009.html").write_text(
        f'<!doctype html><html><body data-source="{URL}">{cards}</body></html>\n',
        encoding="utf-8",
    )
    print(json.dumps({"records": len(records), "screenshot": "live_schedule_20261009.png"}))
    return 0 if len(records) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
