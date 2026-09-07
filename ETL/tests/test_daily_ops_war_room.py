from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "src" / "tools" / "build_daily_ops_war_room.py"
SPEC = importlib.util.spec_from_file_location("build_daily_ops_war_room", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_rendered_dashboard_has_standalone_operational_contract() -> None:
    payload = {
        "date": "2026-09-02",
        "generated_at": "2026-09-03T09:00:00+05:30",
        "summary": {},
        "prior": {},
        "source_rows": [],
        "minute": [],
        "channels": [],
        "identity": [],
        "latency": {},
        "hourly": [],
        "statuses": [],
        "cache": [],
        "hosts": [],
        "content": [],
        "devices": [],
        "markets": [],
        "asns": [],
        "bandwidth": {},
    }

    page = MODULE.render_html(payload)

    assert "02 SEP 2026 | WED" in page
    assert "AUDIENCE PULSE" in page
    assert "DELIVERY QUALITY" in page
    assert "CHANNELS &amp; STREAM CONTENT" in page
    assert "Export daily summary CSV" in page
    assert '<script id="etl-data" type="application/json">' in page
    assert "No revenue, social, score, or broadcast status fabricated" in page
    assert "TOTAL REVENUE" not in page
    assert "POSITIVE SENTIMENT" not in page
    assert "MATCH IN PROGRESS" not in page


def test_project_mart_paths_are_processed_outputs() -> None:
    for path in MODULE.MARTS.values():
        assert "output" in path.parts
        assert "data" not in path.parts or "master" in path.parts
