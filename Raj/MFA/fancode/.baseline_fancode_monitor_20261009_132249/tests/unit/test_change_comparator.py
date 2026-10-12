"""
Unit tests for StateComparator (Phase 8).
"""

from datetime import datetime, timezone
import pytest
from app.change_detection.comparator import StateComparator


class TestStateComparator:
    def test_normalize_for_comparison_whitespace(self):
        assert StateComparator.normalize_for_comparison("   Hello    World   ") == "Hello World"
        assert StateComparator.normalize_for_comparison("") is None
        assert StateComparator.normalize_for_comparison("   ") is None
        assert StateComparator.normalize_for_comparison(None) is None

    def test_normalize_for_comparison_url(self):
        url1 = "https://www.fancode.com/match/123/?utm_source=test#header"
        url2 = "https://www.fancode.com/match/123"
        # URL normalizer canonicalizes strip queries and fragments
        assert StateComparator.normalize_for_comparison(url1) == "https://www.fancode.com/match/123"
        assert StateComparator.normalize_for_comparison(url2) == "https://www.fancode.com/match/123"

    def test_normalize_for_comparison_datetime(self):
        dt_naive = datetime(2026, 5, 10, 14, 0, 0)
        dt_utc = datetime(2026, 5, 10, 14, 0, 0, tzinfo=timezone.utc)
        assert StateComparator.normalize_for_comparison(dt_naive) == "2026-05-10T14:00:00Z"
        assert StateComparator.normalize_for_comparison(dt_utc) == "2026-05-10T14:00:00Z"

    def test_normalize_for_comparison_primitives(self):
        assert StateComparator.normalize_for_comparison(123) == "123"
        assert StateComparator.normalize_for_comparison(True) == "true"
        assert StateComparator.normalize_for_comparison(False) == "false"

    def test_are_values_equal_identical(self):
        assert StateComparator.are_values_equal("Wankhede", "Wankhede")
        assert StateComparator.are_values_equal("  Wankhede  ", "Wankhede")

    def test_are_values_equal_null_safety(self):
        # Section 15 rule: If new_val is None, it was unobserved, so it must NOT be treated as a change
        assert StateComparator.are_values_equal("Existing Venue", None) is True
        # But if old_val is None and new_val is present, it's newly populated (change)
        assert StateComparator.are_values_equal(None, "New Venue") is False

    def test_are_values_equal_different_values(self):
        assert StateComparator.are_values_equal("Venue A", "Venue B") is False
        assert StateComparator.are_values_equal(100, 200) is False

    def test_compare_fields_only_detects_changes(self):
        old_data = {"title": "Match 1", "venue": "Stadium A", "status": "UPCOMING"}
        new_data = {"title": "Match 1", "venue": "Stadium B", "status": "UPCOMING"}
        tracked = ["title", "venue", "status"]

        diff = StateComparator.compare_fields(old_data, new_data, tracked)
        assert "venue" in diff
        assert diff["venue"] == ("Stadium A", "Stadium B")
        assert "title" not in diff
        assert "status" not in diff

    def test_compute_fingerprint_deterministic(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        fp1 = StateComparator.compute_entity_fingerprint(d1)
        fp2 = StateComparator.compute_entity_fingerprint(d2)
        assert fp1 == fp2
        assert len(fp1) == 64
