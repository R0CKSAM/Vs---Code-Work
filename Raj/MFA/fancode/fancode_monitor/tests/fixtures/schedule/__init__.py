"""
Fixtures for deterministic unit testing of the schedule parser and normalizer.
"""

from typing import Any, Dict

SAMPLE_CRICKET_MATCH: Dict[str, Any] = {
    "id": "match-901",
    "title": "India vs Australia 1st ODI",
    "status": "upcoming",
    "matchDate": "2026-04-15T09:30:00Z",
    "venue": "Eden Gardens, Kolkata",
    "sport": {"id": "1", "name": "Cricket"},
    "tour": {"id": "10", "name": "Australia Tour of India 2026"},
    "teamA": {"name": "India", "id": "ind-1", "logoUrl": "https://img.fancode.com/ind.png"},
    "teamB": {"name": "Australia", "id": "aus-1", "logoUrl": "https://img.fancode.com/aus.png"},
    "source_url": "https://www.fancode.com/matches/ind-vs-aus-1st-odi",
}

SAMPLE_FOOTBALL_MATCH: Dict[str, Any] = {
    "matchId": "fb-888",
    "eventName": "Arsenal vs Chelsea",
    "matchStatus": "live",
    "startTime": "2026-04-18T18:00:00Z",
    "sportName": "Football",
    "tournament": {"id": "pl-1", "name": "Premier League"},
    "teams": [
        {"name": "Arsenal", "id": "ars-1"},
        {"name": "Chelsea", "id": "che-1"},
    ],
    "url": "https://www.fancode.com/matches/arsenal-vs-chelsea",
}

SAMPLE_INDIVIDUAL_EVENT: Dict[str, Any] = {
    "id": "f1-100",
    "title": "Monaco Grand Prix Qualifying",
    "status": "scheduled",
    "sport": {"name": "Formula 1"},
    "matchDate": "2026-05-23T13:00:00Z",
    "venue": "Circuit de Monaco",
}

SAMPLE_MALFORMED_ITEM: Dict[str, Any] = {
    "invalid_key": 12345,
    "no_title_or_teams": True,
}

SAMPLE_DUPLICATE_ITEMS = [
    {
        "id": "match-dup-1",
        "title": "MI vs CSK",
        "status": "live",
        "url": "https://www.fancode.com/matches/mi-vs-csk",
    },
    {
        "id": "match-dup-1",
        "title": "MI vs CSK Updated",
        "status": "completed",
        "url": "https://www.fancode.com/matches/mi-vs-csk",
    },
]
