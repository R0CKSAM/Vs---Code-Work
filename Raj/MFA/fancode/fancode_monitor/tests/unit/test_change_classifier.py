"""
Unit tests for ChangeClassifier (Phase 8).
"""

import pytest
from app.change_detection.classifier import ChangeClassifier
from app.change_detection.models import ChangeType, EntityType, Severity


class TestChangeClassifier:
    def test_meaningful_fields_allowlist(self):
        assert ChangeClassifier.is_meaningful_field("MATCH", "venue") is True
        assert ChangeClassifier.is_meaningful_field("MATCH", "status") is True
        assert ChangeClassifier.is_meaningful_field("MATCH", "start_time") is True
        assert ChangeClassifier.is_meaningful_field("VIDEO", "title") is True
        assert ChangeClassifier.is_meaningful_field("VIDEO", "duration_seconds") is True

    def test_noisy_fields_blocklist(self):
        # Score, overs, wickets are strictly volatile operational data, not change events
        assert ChangeClassifier.is_noisy_field("MATCH", "score_summary") is True
        assert ChangeClassifier.is_noisy_field("MATCH", "score") is True
        assert ChangeClassifier.is_noisy_field("MATCH", "overs") is True
        assert ChangeClassifier.is_noisy_field("MATCH", "wickets") is True
        assert ChangeClassifier.is_noisy_field("MATCH", "last_seen_at") is True
        assert ChangeClassifier.is_meaningful_field("MATCH", "score_summary") is False

    def test_status_transitions(self):
        # UPCOMING -> LIVE is CRITICAL
        ctype, sev = ChangeClassifier.classify_field_change("MATCH", "status", "UPCOMING", "LIVE")
        assert ctype == ChangeType.STATUS_CHANGED.value
        assert sev == Severity.CRITICAL.value

        # LIVE -> COMPLETED is IMPORTANT
        ctype, sev = ChangeClassifier.classify_field_change("MATCH", "status", "LIVE", "COMPLETED")
        assert ctype == ChangeType.STATUS_CHANGED.value
        assert sev == Severity.IMPORTANT.value

        # Any -> CANCELLED is CRITICAL
        ctype, sev = ChangeClassifier.classify_field_change("MATCH", "status", "UPCOMING", "CANCELLED")
        assert ctype == ChangeType.STATUS_CHANGED.value
        assert sev == Severity.CRITICAL.value

    def test_generic_field_update(self):
        ctype, sev = ChangeClassifier.classify_field_change("MATCH", "venue", "Wankhede", "DY Patil")
        assert ctype == ChangeType.UPDATED.value
        assert sev == Severity.IMPORTANT.value

    def test_untracked_match_description_is_suppressed(self):
        assert ChangeClassifier.is_noisy_field("MATCH", "description") is True
        assert ChangeClassifier.is_meaningful_field("MATCH", "description") is False
        assert ChangeClassifier.classify_field_change("MATCH", "description", "Old", "New") is None

    def test_placeholder_title_churn_is_suppressed_in_both_directions(self):
        assert ChangeClassifier.classify_field_change(
            "MATCH", "title", "Match 2", "Tasmania vs New South Wales"
        ) is None
        assert ChangeClassifier.classify_field_change(
            "MATCH", "title", "Tasmania vs New South Wales", "Match 2"
        ) is None
