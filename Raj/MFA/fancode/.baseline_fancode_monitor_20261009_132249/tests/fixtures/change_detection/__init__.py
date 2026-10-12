"""
Test fixtures for Change Detection Engine (Phase 8).
"""

SAMPLE_MATCH_A_SCHEDULED = {
    "match_id": "match-101",
    "external_id": "101",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "UPCOMING",
    "venue": "Wankhede Stadium, Mumbai",
    "start_time": "2026-05-10T14:00:00Z",
    "team_a_name": "Mumbai Indians",
    "team_b_name": "Chennai Super Kings",
    "score_summary": None,
    "source_url": "https://www.fancode.com/match/101",
}

# Only score changed: 120/3 -> 121/3 (Volatile noise, must NOT trigger event)
SAMPLE_MATCH_A_SCORE_NOISE = {
    "match_id": "match-101",
    "external_id": "101",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "UPCOMING",
    "venue": "Wankhede Stadium, Mumbai",
    "start_time": "2026-05-10T14:00:00Z",
    "team_a_name": "Mumbai Indians",
    "team_b_name": "Chennai Super Kings",
    "score_summary": "121/3 in 15.2 ov",
    "source_url": "https://www.fancode.com/match/101",
}

# Status changed: UPCOMING -> LIVE (CRITICAL/IMPORTANT event)
SAMPLE_MATCH_A_WENT_LIVE = {
    "match_id": "match-101",
    "external_id": "101",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "LIVE",
    "venue": "Wankhede Stadium, Mumbai",
    "start_time": "2026-05-10T14:00:00Z",
    "team_a_name": "Mumbai Indians",
    "team_b_name": "Chennai Super Kings",
    "score_summary": "125/3 in 16.0 ov",
    "source_url": "https://www.fancode.com/match/101",
}

# Venue rescheduled / updated
SAMPLE_MATCH_A_RESCHEDULED = {
    "match_id": "match-101",
    "external_id": "101",
    "title": "Mumbai Indians vs Chennai Super Kings",
    "status": "UPCOMING",
    "venue": "DY Patil Stadium, Navi Mumbai",
    "start_time": "2026-05-10T15:30:00Z",
    "team_a_name": "Mumbai Indians",
    "team_b_name": "Chennai Super Kings",
    "source_url": "https://www.fancode.com/match/101",
}

SAMPLE_VIDEO_NEW = {
    "slug": "mumbai-vs-chennai-best-wickets",
    "external_id": "vid-901",
    "title": "Best Wickets - MI vs CSK 2026",
    "video_type": "HIGHLIGHTS",
    "duration_seconds": 320,
    "source_url": "https://www.fancode.com/video/vid-901",
}
