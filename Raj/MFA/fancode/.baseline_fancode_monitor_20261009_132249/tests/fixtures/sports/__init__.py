"""
Fixtures for Sports unit tests.
"""

from typing import Any, Dict

SAMPLE_SPORT_NORMAL: Dict[str, Any] = {
    "id": "sport-1",
    "name": "Cricket",
    "slug": "cricket",
    "description": "Live cricket streaming and matches",
    "imageUrl": "https://img.fancode.com/cricket.png",
    "isActive": True,
    "url": "https://www.fancode.com/cricket",
}

SAMPLE_SPORT_NO_IMAGE: Dict[str, Any] = {
    "sportId": "sport-2",
    "sportName": "Football",
    "slug": "football",
}

SAMPLE_SPORT_NO_ID: Dict[str, Any] = {
    "name": "Kabaddi",
    "url": "https://www.fancode.com/kabaddi",
}

SAMPLE_SPORT_MALFORMED: Dict[str, Any] = {
    "invalid_data": True,
    "score": 100,
}

SAMPLE_SPORT_DUPLICATES = [
    {"name": "Basketball", "slug": "basketball", "url": "https://www.fancode.com/basketball"},
    {"name": "Basketball", "slug": "basketball", "url": "https://www.fancode.com/basketball"},
]
