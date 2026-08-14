from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ETL.src.common.publication_dates import latest_completed_ist_date


NOW = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_publication_date_defaults_to_yesterday() -> None:
    assert latest_completed_ist_date(environ={}, now=NOW).isoformat() == "2026-08-12"


def test_publication_date_can_be_capped_to_validated_day() -> None:
    env = {"VG_DASH_COMPLETED_THROUGH": "2026-08-09"}
    assert latest_completed_ist_date(environ=env, now=NOW).isoformat() == "2026-08-09"


def test_publication_date_never_exposes_current_or_future_day() -> None:
    env = {"VG_DASH_COMPLETED_THROUGH": "2026-08-20"}
    assert latest_completed_ist_date(environ=env, now=NOW).isoformat() == "2026-08-12"


def test_publication_date_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        latest_completed_ist_date(environ={"VG_DASH_COMPLETED_THROUGH": "09-08-2026"}, now=NOW)
