import json
from pathlib import Path

from app.scraper.schedule.models import RawScheduleItem
from app.scraper.schedule.parser import ScheduleParser


def test_captured_live_schedule_fixture_parses_offline():
    fixture = Path(__file__).parents[1] / "fixtures" / "schedule" / "live_schedule_20261009.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    assert payload["source_url"] == "https://www.fancode.com/schedule"
    assert len(payload["records"]) == 5
    parsed = [ScheduleParser.parse_item(RawScheduleItem(raw_data=item)) for item in payload["records"]]
    assert all(item is not None for item in parsed)
    assert all(item.external_id and item.source_url.startswith("https://www.fancode.com/") for item in parsed)
    assert all(f"-{item.external_id}/" in item.source_url for item in parsed)
