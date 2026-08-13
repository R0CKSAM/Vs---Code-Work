from pathlib import Path


def test_neighbourhood_default_view_uses_latest_two_weeks():
    script_path = Path(__file__).resolve().parents[1] / "static" / "neighbourhood.js"
    script_text = script_path.read_text(encoding="utf-8")

    assert "const DEFAULT_VISIBLE_WEEK_COUNT = 2;" in script_text
    assert "return allWeeks.slice(Math.max(0, allWeeks.length - DEFAULT_VISIBLE_WEEK_COUNT));" in script_text
