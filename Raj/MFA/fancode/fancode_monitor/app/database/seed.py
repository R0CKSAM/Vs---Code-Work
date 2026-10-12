"""
seed.py – Deterministic test & development seed helpers.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.database.connection import get_session
from app.database.models import Sport, Tour
from app.database.repositories import SportsRepository, ToursRepository


def seed_sample_data(session: Optional[Session] = None) -> None:
    """Seed minimal initial reference data if not already present."""
    def _do_seed(s: Session) -> None:
        sports_repo = SportsRepository(s)
        tours_repo = ToursRepository(s)

        cricket = sports_repo.upsert(
            name="Cricket",
            slug="cricket",
            source_url="https://www.fancode.com/cricket",
            is_active=True,
        )

        tours_repo.upsert(
            name="Indian Premier League",
            slug="ipl-2026",
            source_url="https://www.fancode.com/tours/ipl-2026",
            sport_id=cricket.id,
            status="UPCOMING",
        )

    if session:
        _do_seed(session)
    else:
        with get_session() as sess:
            _do_seed(sess)
