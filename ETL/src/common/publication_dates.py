"""Shared completed-day cutoff used when publishing static dashboards."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo


PUBLICATION_CUTOFF_ENV = "VG_DASH_COMPLETED_THROUGH"
IST = ZoneInfo("Asia/Kolkata")


def latest_completed_ist_date(
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> date:
    """Return yesterday in IST, optionally capped by an explicit publish-through date."""
    values = os.environ if environ is None else environ
    current = now.astimezone(IST) if now is not None else datetime.now(IST)
    natural_cutoff = current.date() - timedelta(days=1)
    raw = str(values.get(PUBLICATION_CUTOFF_ENV, "")).strip()
    if not raw:
        return natural_cutoff
    try:
        requested = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"{PUBLICATION_CUTOFF_ENV} must be YYYY-MM-DD; received {raw!r}."
        ) from exc
    return min(requested, natural_cutoff)


def latest_completed_ist_date_text(**kwargs) -> str:
    return latest_completed_ist_date(**kwargs).isoformat()
