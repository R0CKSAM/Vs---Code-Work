"""
test_discovery_unit.py – Unit tests for Discovery Engine components.

Tests components without requiring live network access or live FanCode:
- URL normalization & relative resolving
- Tracking parameter removal
- Duplicate detection
- Internal vs external domain restriction
- Page classification (URL patterns & fallback titles)
- Network event filtering & parsing
- Models serialization and helper properties
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.discovery.models import (
    DiscoveredPage,
    DiscoveryResult,
    NetworkEvent,
    PageType,
)
from app.scraper.discovery.page_classifier import classify_page, classify_url
from app.scraper.discovery.url_normalizer import (
    are_duplicates,
    deduplicate,
    is_internal,
    normalize,
)


class TestUrlNormalizer:
    """Test URL normalization, filtering, and resolution."""

    def test_normalize_relative_url(self) -> None:
        norm = normalize("/cricket", "https://www.fancode.com")
        assert norm == "https://www.fancode.com/cricket"

    def test_normalize_strips_trailing_slash_except_root(self) -> None:
        root = normalize("/", "https://www.fancode.com")
        assert root == "https://www.fancode.com/"

        page = normalize("/schedule/", "https://www.fancode.com")
        assert page == "https://www.fancode.com/schedule"

    def test_normalize_removes_fragment(self) -> None:
        url = normalize("/matches/123#lineups", "https://www.fancode.com")
        assert url == "https://www.fancode.com/matches/123"

    def test_normalize_removes_tracking_params_preserves_content_params(self) -> None:
        raw = "/schedule?tab=cricket&utm_source=google&ref=twitter&sort=date"
        norm = normalize(raw, "https://www.fancode.com")
        assert norm is not None
        assert "utm_source" not in norm
        assert "ref=" not in norm
        assert "tab=cricket" in norm
        assert "sort=date" in norm

    def test_normalize_external_url_returns_none(self) -> None:
        assert normalize("https://www.google.com/search", "https://www.fancode.com") is None
        assert normalize("https://facebook.com", "https://www.fancode.com") is None

    def test_normalize_invalid_or_action_urls(self) -> None:
        assert normalize("javascript:void(0)", "https://www.fancode.com") is None
        assert normalize("mailto:support@fancode.com", "https://www.fancode.com") is None
        assert normalize("tel:+1234567890", "https://www.fancode.com") is None
        assert normalize("#top", "https://www.fancode.com") is None
        assert normalize("", "https://www.fancode.com") is None

    def test_is_internal(self) -> None:
        assert is_internal("https://www.fancode.com/cricket") is True
        assert is_internal("https://fancode.com/live") is True
        assert is_internal("https://subdomain.fancode.com/tour") is True
        assert is_internal("https://www.google.com") is False
        assert is_internal("https://notfancode.com") is False

    def test_deduplicate(self) -> None:
        urls = [
            "https://www.fancode.com/cricket",
            "https://www.fancode.com/live",
            "https://www.fancode.com/cricket",
            "https://www.fancode.com/schedule",
            "https://www.fancode.com/live",
        ]
        deduped = deduplicate(urls)
        assert deduped == [
            "https://www.fancode.com/cricket",
            "https://www.fancode.com/live",
            "https://www.fancode.com/schedule",
        ]

    def test_are_duplicates(self) -> None:
        u1 = "https://www.fancode.com/live"
        u2 = "https://www.fancode.com/live"
        u3 = "https://www.fancode.com/schedule"
        assert are_duplicates(u1, u2) is True
        assert are_duplicates(u1, u3) is False


class TestPageClassifier:
    """Test deterministic page classification."""

    def test_classify_home(self) -> None:
        assert classify_url("https://www.fancode.com") == PageType.HOME
        assert classify_url("https://www.fancode.com/") == PageType.HOME

    def test_classify_schedule(self) -> None:
        assert classify_url("https://www.fancode.com/schedule") == PageType.SCHEDULE

    def test_classify_live(self) -> None:
        assert classify_url("https://www.fancode.com/live") == PageType.LIVE
        assert classify_url("https://www.fancode.com/live-now") == PageType.LIVE

    def test_classify_matches(self) -> None:
        assert classify_url("https://www.fancode.com/matches/ind-vs-aus") == PageType.MATCH
        assert classify_url("https://www.fancode.com/match/1234") == PageType.MATCH

    def test_classify_series_tour(self) -> None:
        assert classify_url("https://www.fancode.com/series/ipl-2026") == PageType.SERIES
        assert classify_url("https://www.fancode.com/tours/eng-tour") == PageType.TOUR

    def test_classify_sport(self) -> None:
        assert classify_url("https://www.fancode.com/sports") == PageType.SPORT
        assert classify_url("https://www.fancode.com/cricket") == PageType.SPORT
        assert classify_url("https://www.fancode.com/football") == PageType.SPORT

    def test_classify_video(self) -> None:
        assert classify_url("https://www.fancode.com/video/highlight-1") == PageType.VIDEO
        assert classify_url("https://www.fancode.com/watch/replay") == PageType.VIDEO

    def test_classify_team_and_player(self) -> None:
        assert classify_url("https://www.fancode.com/teams/mumbai-indians") == PageType.TEAM
        assert classify_url("https://www.fancode.com/players/rohit-sharma") == PageType.PLAYER

    def test_classify_unknown(self) -> None:
        assert classify_url("https://www.fancode.com/about-us") == PageType.UNKNOWN

    def test_classify_page_title_fallback(self) -> None:
        # URL pattern is unknown, fallback to title
        res = classify_page("https://www.fancode.com/custom-section", "Live Cricket Stream Online")
        assert res == PageType.LIVE

        res_sched = classify_page("https://www.fancode.com/fixtures", "Match Schedule & Fixtures")
        assert res_sched == PageType.SCHEDULE


class TestDiscoveryModels:
    """Test data model properties, serialization, and aggregation."""

    def test_network_event_to_dict(self) -> None:
        evt = NetworkEvent(
            url="https://api.fancode.com/matches",
            method="GET",
            resource_type="fetch",
            status=200,
            content_type="application/json",
            is_json=True,
            observed_on="https://www.fancode.com/",
        )
        data = evt.to_dict()
        assert data["url"] == "https://api.fancode.com/matches"
        assert data["status"] == 200
        assert data["is_json"] is True

    def test_discovered_page_json_endpoints(self) -> None:
        evt_json = NetworkEvent(
            url="https://api.fancode.com/data",
            method="GET",
            resource_type="fetch",
            status=200,
            content_type="application/json",
            is_json=True,
        )
        evt_doc = NetworkEvent(
            url="https://www.fancode.com/page",
            method="GET",
            resource_type="document",
            status=200,
            content_type="text/html",
            is_json=False,
        )
        page = DiscoveredPage(
            url="https://www.fancode.com/",
            canonical_url="https://www.fancode.com/",
            title="FanCode Home",
            page_type=PageType.HOME,
            depth=0,
            http_status=200,
            network_events=[evt_json, evt_doc],
        )
        assert len(page.json_endpoints) == 1
        assert page.json_endpoints[0].url == "https://api.fancode.com/data"

    def test_discovery_result_aggregations(self) -> None:
        p1 = DiscoveredPage(
            url="https://www.fancode.com/",
            canonical_url="https://www.fancode.com/",
            title="Home",
            page_type=PageType.HOME,
            depth=0,
            http_status=200,
        )
        p2 = DiscoveredPage(
            url="https://www.fancode.com/cricket",
            canonical_url="https://www.fancode.com/cricket",
            title="Cricket",
            page_type=PageType.SPORT,
            depth=1,
            http_status=200,
        )
        result = DiscoveryResult(
            base_url="https://www.fancode.com",
            pages=[p1, p2],
        )
        assert result.page_count == 2
        assert len(result.unique_urls) == 2
        by_type = result.pages_by_type
        assert "HOME" in by_type
        assert "SPORT" in by_type
        assert len(by_type["HOME"]) == 1
