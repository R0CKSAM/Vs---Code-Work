"""
Fixtures for Tours unit tests.
"""

from typing import Any, Dict

SAMPLE_TOUR_NORMAL: Dict[str, Any] = {
    "id": "tour-101",
    "name": "Indian Premier League 2026",
    "slug": "ipl-2026",
    "description": "Premier T20 Cricket league",
    "imageUrl": "https://img.fancode.com/ipl-banner.png",
    "startDate": "2026-03-25T14:00:00Z",
    "endDate": "2026-05-30T18:00:00Z",
    "status": "upcoming",
    "sport": {"id": "sport-1", "name": "Cricket"},
    "url": "https://www.fancode.com/tours/ipl-2026",
}

SAMPLE_TOUR_NO_DATES: Dict[str, Any] = {
    "tourId": "tour-102",
    "tourName": "English Premier League",
    "slug": "epl-2026",
    "sportName": "Football",
    "url": "https://www.fancode.com/tours/epl-2026",
}

SAMPLE_TOUR_MALFORMED: Dict[str, Any] = {
    "unknown_key": "some value",
}

SAMPLE_TOUR_DUPLICATES = [
    {"name": "Caribbean Premier League", "slug": "cpl-2026", "url": "https://www.fancode.com/tours/cpl-2026"},
    {"name": "Caribbean Premier League", "slug": "cpl-2026", "url": "https://www.fancode.com/tours/cpl-2026"},
]
