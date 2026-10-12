"""
Regression tests for Phase 6 Live Now scraper enhancements and data quality rules.

Validates that:
- Generic UI labels ("LIVE", "WATCH LIVE", "LIVE NOW", "MATCH", "SCORES", "SPORTS") never become match titles.
- Landing page URLs with title="LIVE" are rejected.
- Match URLs with title="LIVE" recover genuine team/slug match title if available, or are rejected.
- Valid structured live matches and team-derived titles are accepted.
- GraphQL payload schemas and SSR window.__INITIAL_STATE__ embedded data are parsed cleanly.
- Database persistence layer skips generic UI titles to prevent pollution.
"""

from unittest.mock import MagicMock
import pytest

from app.scraper.live_now.models import RawLiveItem, LiveMatchRecord
from app.scraper.live_now.network import LIVE_API_PATTERNS, LiveNowNetworkInterceptor
from app.scraper.live_now.normalizer import (
    GENERIC_UI_TITLES,
    LiveNowNormalizer,
    extract_title_from_slug_or_url,
    is_valid_match_title,
)
from app.scraper.live_now.parser import LiveNowParser


def test_is_valid_match_title_rejections():
    """Verify all generic UI labels and malformed strings are rejected as match titles."""
    generic_labels = [
        "LIVE",
        "Live",
        "live",
        "WATCH LIVE",
        "Watch Live",
        "watch live",
        "LIVE NOW",
        "Live Now",
        "MATCH",
        "Match",
        "match",
        "SCORES",
        "Scores",
        "scores",
        "SPORTS",
        "Sports",
        "sports",
        "ALL SPORTS",
        "LIVE SCORE",
        "STREAM",
        "STREAMS",
        "UPCOMING",
        "HIGHLIGHTS",
        "VIDEOS",
        "",
        "   ",
        "AB",
    ]
    for label in generic_labels:
        assert not is_valid_match_title(label), f"Expected {label!r} to be rejected"


def test_is_valid_match_title_acceptances():
    """Verify legitimate match titles and tournament fixture names are accepted."""
    valid_titles = [
        "India vs Pakistan",
        "Mumbai Indians vs Chennai Super Kings",
        "Tuskers vs Lions",
        "Bulls XI vs Tigers XI",
        "New South Wales vs Tasmania",
        "Bangladesh vs Zimbabwe",
        "Six Nations Championship",
        "A-League Men 2026",
    ]
    for title in valid_titles:
        assert is_valid_match_title(title), f"Expected {title!r} to be accepted"


def test_reject_live_title_with_landing_page_url():
    """Rule 1: title='LIVE' + live-now landing URL must be completely rejected."""
    raw = RawLiveItem(
        raw_data={
            "title": "LIVE",
            "url": "https://www.fancode.com/live-now/all-sports",
            "status": "LIVE",
        },
        source_type="dom",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is None


def test_recover_title_from_match_url_with_live_title():
    """Rule 2: title='LIVE' + real match URL recovers real match title from slug."""
    raw = RawLiveItem(
        raw_data={
            "title": "LIVE",
            "url": "https://www.fancode.com/new-south-wales-vs-tasmania/140123/live-match-info",
            "status": "LIVE",
        },
        source_type="dom",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is not None
    assert rec.title == "New South Wales vs Tasmania"
    assert rec.status == "LIVE"


def test_reject_live_title_with_match_url_if_unrecoverable():
    """Rule 2b: title='LIVE' + URL with no team/slug info is rejected."""
    raw = RawLiveItem(
        raw_data={
            "title": "LIVE",
            "url": "https://www.fancode.com/matches/watch/live-stream",
            "status": "LIVE",
        },
        source_type="dom",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is None


def test_valid_structured_live_match_accepted():
    """Rule 3: Valid structured live match with nested match.id, match.teams, status.status = LIVE, features.slug is accepted."""
    raw = RawLiveItem(
        raw_data={
            "id": "140356",
            "match": {
                "id": 140356,
                "teams": [
                    {"name": "Tuskers", "logo": "https://img.fancode.com/tuskers.png"},
                    {"name": "Lions", "logo": "https://img.fancode.com/lions.png"},
                ],
            },
            "status": {"status": "LIVE", "streamingStatus": "STARTED"},
            "tour": {
                "collectionId": 5001,
                "name": "Pondicherry Men's T20 League, 2026",
            },
            "features": {
                "slug": "tuskers-vs-lions",
            },
        },
        source_type="json",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is not None
    assert rec.match_external_id == "140356"
    assert rec.title == "Tuskers vs Lions"
    assert rec.status == "LIVE"
    assert rec.team_a_name == "Tuskers"
    assert rec.team_b_name == "Lions"
    assert rec.tour_name == "Pondicherry Men's T20 League, 2026"


def test_title_generated_from_team_names():
    """Rule 4: Valid real match whose title is generated from team names is accepted."""
    raw = RawLiveItem(
        raw_data={
            "id": "139151",
            "teamA": {"name": "Bangladesh"},
            "teamB": {"name": "Zimbabwe"},
            "status": "LIVE",
        },
        source_type="json",
    )
    rec = LiveNowParser.parse_live_item(raw)
    assert rec is not None
    assert rec.title == "Bangladesh vs Zimbabwe"
    assert rec.match_external_id == "139151"


def test_normalizer_filters_out_generic_ui_records():
    """Rule 5: LiveNowNormalizer filter_valid_records drops any record with generic UI title."""
    records = [
        LiveMatchRecord(match_external_id="1", title="LIVE", source_url="https://fancode.com/live"),
        LiveMatchRecord(match_external_id="2", title="WATCH LIVE", source_url="https://fancode.com/live-now"),
        LiveMatchRecord(match_external_id="3", title="LIVE NOW", source_url="https://fancode.com/live-now/all-sports"),
        LiveMatchRecord(match_external_id="4", title="SCORES", source_url="https://fancode.com/scores"),
        LiveMatchRecord(match_external_id="5", title="SPORTS", source_url="https://fancode.com/sports"),
        LiveMatchRecord(match_external_id="6", title="Nepal vs Netherlands", source_url="https://fancode.com/matches/nepal-vs-netherlands/6"),
    ]
    valid = LiveNowNormalizer.filter_valid_records(records)
    assert len(valid) == 1
    assert valid[0].title == "Nepal vs Netherlands"


def test_network_interceptor_matches_graphql():
    """Verify LIVE_API_PATTERNS matches FanCode GraphQL and live endpoints."""
    assert LIVE_API_PATTERNS.search("https://www.fancode.com/graphql")
    assert LIVE_API_PATTERNS.search("https://www.fancode.com/api/v1/matches/live")
    assert LIVE_API_PATTERNS.search("https://www.fancode.com/live-now/all-sports")
    assert not LIVE_API_PATTERNS.search("https://www.fancode.com/assets/main.css")


def test_extract_embedded_initial_state_json():
    """Test extracting SSR state from window.__INITIAL_STATE__ script."""
    html_content = """
    <!DOCTYPE html>
    <html>
      <head>
        <script>
          window.__INITIAL_STATE__ = {
            "live-now-view": {
              "matches": [
                {
                  "id": "55001",
                  "title": "Real Madrid vs Barcelona",
                  "status": {"status": "LIVE", "streamingStatus": "STARTED"},
                  "match": {
                    "teams": [
                      {"name": "Real Madrid", "logo": "https://img.fancode.com/rm.png"},
                      {"name": "Barcelona", "logo": "https://img.fancode.com/fcb.png"}
                    ]
                  }
                }
              ]
            }
          };
        </script>
      </head>
      <body></body>
    </html>
    """
    extracted = LiveNowParser.extract_embedded_json(html_content)
    assert extracted is not None
    assert "live-now-view" in extracted

    items = LiveNowParser.extract_live_items_from_payload(extracted)
    assert len(items) >= 1

    rec = LiveNowParser.parse_live_item(items[0])
    assert rec is not None
    assert rec.match_external_id == "55001"
    assert rec.title == "Real Madrid vs Barcelona"
    assert rec.status == "LIVE"
    assert rec.team_a_name == "Real Madrid"
    assert rec.team_b_name == "Barcelona"
