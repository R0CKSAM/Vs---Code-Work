"""Regression tests for Audience Operations completed-day publication."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "dashboards"
    / "audienceOpsDashboard"
    / "generate_audience_ops.py"
)
SPEC = importlib.util.spec_from_file_location("generate_audience_ops", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
audience_ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audience_ops)


def minute_rows(day: str, source: str, count: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "log_date": [day] * count,
            "source": [source] * count,
            "minute_ist": pd.date_range(day, periods=count, freq="min"),
        }
    )


def test_all_scope_rejects_a_day_when_either_source_is_partial() -> None:
    minute = pd.concat(
        [
            minute_rows("2026-08-10", "fast", 1440),
            minute_rows("2026-08-10", "stream", 1440),
            minute_rows("2026-08-11", "fast", 1440),
            minute_rows("2026-08-11", "stream", 330),
        ],
        ignore_index=True,
    )

    assert str(audience_ops.latest_complete_minute_date(minute, "all")) == "2026-08-10"
    assert str(audience_ops.latest_complete_minute_date(minute, "fast")) == "2026-08-11"


def test_non_cdn_scope_does_not_apply_fast_stream_gate() -> None:
    minute = minute_rows("2026-08-10", "amagi", 1440)

    assert audience_ops.latest_complete_minute_date(minute, "amagi") is None
