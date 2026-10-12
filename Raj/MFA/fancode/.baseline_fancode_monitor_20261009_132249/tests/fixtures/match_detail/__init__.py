"""
Fixtures for Match Detail unit tests.
"""

from typing import Any, Dict

SAMPLE_MATCH_DETAIL_NORMAL: Dict[str, Any] = {
    "id": "match-501",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "scheduled",
    "matchDate": "2026-04-20T14:00:00Z",
    "venue": "Wankhede Stadium",
    "city": "Mumbai",
    "country": "India",
    "sport": {"id": "1", "name": "Cricket"},
    "tour": {"id": "10", "name": "Indian Premier League 2026"},
    "teamA": {"name": "Mumbai Indians", "id": "mi-1", "logoUrl": "https://img.fancode.com/mi.png"},
    "teamB": {"name": "Chennai Super Kings", "id": "csk-1", "logoUrl": "https://img.fancode.com/csk.png"},
    "scoreSummary": "Match yet to begin",
    "description": "Epic rivalry clash in IPL 2026",
    "imageUrl": "https://img.fancode.com/banner-mi-csk.png",
    "isStreaming": True,
    "language": "English",
    "source_url": "https://www.fancode.com/matches/mi-vs-csk-ipl-2026",
}

SAMPLE_MATCH_DETAIL_NO_VENUE: Dict[str, Any] = {
    "id": "match-502",
    "title": "Arsenal vs Chelsea",
    "status": "live",
    "matchDate": "2026-04-22T19:00:00Z",
    "sportName": "Football",
    "teamA": {"name": "Arsenal"},
    "teamB": {"name": "Chelsea"},
    "source_url": "https://www.fancode.com/matches/ars-vs-che",
}

SAMPLE_MATCH_DETAIL_COMPLETED: Dict[str, Any] = {
    "id": "match-503",
    "title": "India vs Pakistan T20",
    "status": "completed",
    "scoreSummary": "IND 180/5, PAK 160/9 (IND won by 20 runs)",
    "source_url": "https://www.fancode.com/matches/ind-vs-pak-t20",
}

SAMPLE_MATCH_DETAIL_INDIVIDUAL: Dict[str, Any] = {
    "id": "f1-event-1",
    "title": "Bahrain GP Qualifying",
    "venue": "Bahrain International Circuit",
    "status": "upcoming",
    "source_url": "https://www.fancode.com/matches/bahrain-gp-qualifying",
}

SAMPLE_MATCH_DETAIL_MALFORMED: Dict[str, Any] = {
    "broken_field": True,
}
