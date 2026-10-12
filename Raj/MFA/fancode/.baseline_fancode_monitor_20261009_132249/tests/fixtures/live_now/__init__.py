"""
Fixtures for Live Now parser and normalizer unit tests.
"""

from typing import Any, Dict, List

SAMPLE_LIVE_CRICKET: Dict[str, Any] = {
    "matchId": "crick-live-101",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "live",
    "isLive": True,
    "sport": {"id": "1", "name": "Cricket"},
    "tour": {"id": "10", "name": "Indian Premier League 2026"},
    "teamA": {"id": "mi", "name": "Mumbai Indians", "logoUrl": "https://img.fancode.com/mi.png"},
    "teamB": {"id": "csk", "name": "Chennai Super Kings", "logoUrl": "https://img.fancode.com/csk.png"},
    "venue": {"name": "Wankhede Stadium, Mumbai"},
    "scoreSummary": "MI 152/4 (16.2 ov)",
    "startTime": "2026-04-20T14:00:00Z",
    "liveStartedAt": "2026-04-20T14:05:00Z",
    "isStreaming": True,
    "language": "English",
    "imageUrl": "https://img.fancode.com/live-banner-mi-csk.png",
    "url": "https://www.fancode.com/matches/mi-vs-csk-live",
    "overs": "16.2",
    "matchType": "T20",
}

SAMPLE_LIVE_FOOTBALL: Dict[str, Any] = {
    "id": "fb-live-202",
    "eventName": "Arsenal vs Chelsea",
    "matchStatus": "in_progress",
    "sportName": "Football",
    "tournament": {"id": "epl", "name": "Premier League"},
    "teams": [
        {"id": "ars", "name": "Arsenal", "logoUrl": "https://img.fancode.com/ars.png"},
        {"id": "che", "name": "Chelsea", "logoUrl": "https://img.fancode.com/che.png"},
    ],
    "venue": "Emirates Stadium",
    "score": "ARS 2 - 1 CHE",
    "startTime": "2026-04-22T19:00:00Z",
    "streaming": True,
    "matchUrl": "https://www.fancode.com/matches/ars-vs-che-live",
}

SAMPLE_LIVE_INDIVIDUAL_SPORT: Dict[str, Any] = {
    "eventId": "f1-live-303",
    "name": "Monaco Grand Prix - Race",
    "status": "streaming",
    "sport": {"name": "Motorsport"},
    "venue": "Circuit de Monaco",
    "scoreSummary": "Lap 45/78",
    "startTime": "2026-05-24T13:00:00Z",
    "source_url": "https://www.fancode.com/matches/monaco-gp-live",
}

SAMPLE_LIVE_MISSING_SCORE: Dict[str, Any] = {
    "matchId": "crick-live-104",
    "title": "Kolkata Knight Riders vs Royal Challengers Bengaluru",
    "status": "live",
    "sportName": "Cricket",
    "teamA": {"name": "KKR"},
    "teamB": {"name": "RCB"},
    "venue": "Eden Gardens",
    "url": "https://www.fancode.com/matches/kkr-vs-rcb",
}

SAMPLE_LIVE_MISSING_VENUE: Dict[str, Any] = {
    "matchId": "live-novenue-105",
    "title": "Spain vs Germany",
    "status": "live",
    "sportName": "Football",
    "teams": [{"name": "Spain"}, {"name": "Germany"}],
    "scoreSummary": "0 - 0 (HT)",
    "url": "https://www.fancode.com/matches/esp-vs-ger",
}

SAMPLE_LIVE_MISSING_TEAMS: Dict[str, Any] = {
    "matchId": "live-noteams-106",
    "title": "World Athletics Championship 100m Final",
    "status": "live",
    "sportName": "Athletics",
    "venue": "National Stadium",
    "url": "https://www.fancode.com/matches/athletics-100m",
}

SAMPLE_LIVE_MALFORMED: Dict[str, Any] = {
    "unrelated_key": 9999,
    "garbage": "nonsense",
}

SAMPLE_NESTED_LIVE_PAYLOAD: Dict[str, Any] = {
    "data": {
        "liveSection": {
            "title": "Live Right Now",
            "matches": [
                SAMPLE_LIVE_CRICKET,
                SAMPLE_LIVE_FOOTBALL,
            ],
        },
        "adConfig": {"enabled": False},
    }
}

SAMPLE_MULTIPLE_LIVE_MATCHES: List[Dict[str, Any]] = [
    SAMPLE_LIVE_CRICKET,
    SAMPLE_LIVE_FOOTBALL,
    SAMPLE_LIVE_INDIVIDUAL_SPORT,
]
