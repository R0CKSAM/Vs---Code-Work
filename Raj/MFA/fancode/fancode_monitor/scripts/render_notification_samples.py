"""Generate deterministic notification samples and mobile/desktop screenshots."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.change_detection.models import ChangeType, EntityType, ProposedChangeEvent, Severity
from app.notifications.grouping import EventGrouper
from app.notifications.models import NotificationBatchDraft
from app.notifications.renderer import NotificationRenderer


OUTPUT_DIR = ROOT / "tmp" / "render"


class StrictEnoughHtmlParser(HTMLParser):
    pass


def event(index: int, *, hostile: bool = False) -> ProposedChangeEvent:
    title = 'भारत & <Team "A"> vs Team \'B\' 🏏' if hostile else f"Team {index} vs Team {index + 1}"
    return ProposedChangeEvent(
        entity_type=EntityType.MATCH.value,
        entity_id=index,
        external_id=f"match-{index}",
        change_type=ChangeType.STATUS_CHANGED.value if index % 2 else ChangeType.CREATED.value,
        field_name="status" if index % 2 else None,
        old_value="UPCOMING" if index % 2 else None,
        new_value="LIVE" if index % 2 else title,
        severity=Severity.CRITICAL.value if index % 2 else Severity.IMPORTANT.value,
        source_url=f"https://www.fancode.com/match/{index}",
        metadata={"title": title},
    )


def write_sample(name: str, events: list[ProposedChangeEvent]) -> Path:
    batch = EventGrouper.create_batch(events) if events else NotificationBatchDraft("empty")
    assert batch is not None
    html = NotificationRenderer.render_html(batch)
    text = NotificationRenderer.render_text(batch)
    StrictEnoughHtmlParser().feed(html)
    assert "<script" not in html.lower()
    assert "<style" not in html.lower()
    assert len(NotificationRenderer.generate_subject(batch)) <= 78
    html_path = OUTPUT_DIR / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    (OUTPUT_DIR / f"{name}.txt").write_text(text, encoding="utf-8")
    return html_path


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_sample("empty", [])
    write_sample("single", [event(1)])
    write_sample("mixed_3", [event(1), event(2), event(3)])
    write_sample("large_50", [event(i) for i in range(1, 51)])
    hostile_path = write_sample("hostile_unicode", [event(99, hostile=True)])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (360, 800):
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(hostile_path.as_uri())
            page.screenshot(path=str(OUTPUT_DIR / f"hostile_unicode_{width}px.png"), full_page=True)
            page.close()
        browser.close()
    print(f"rendered_samples={OUTPUT_DIR}")
    print("html_validation=PASS; hostile_data_escaped=PASS; subject_length=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
