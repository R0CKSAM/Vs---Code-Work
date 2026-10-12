"""
test_notification_redesign.py – Comprehensive unit tests for redesigned FanCode email notifications.
Validates executive summary, sequentially numbered cards, entity-specific source links,
'What changed?' / 'Why it matters' sections, safe handling for unverified status transitions,
and suppression of placeholder title changes.
"""

from __future__ import annotations

import html
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.change_detection.classifier import ChangeClassifier, PLACEHOLDER_TITLE_PATTERN
from app.change_detection.models import ChangeType, EntityType, Severity
from app.database.models import ChangeEvent
from app.notifications.grouping import EventGrouper
from app.notifications.models import (
    EmailRecipientConfig,
    GroupedEntity,
    NotificationBatchDraft,
    NotificationStatus,
)
from app.notifications.policy import NotificationPolicy
from app.notifications.renderer import NotificationRenderer


# =============================================================================
# 1. Placeholder Title Suppression Tests
# =============================================================================

@pytest.mark.parametrize(
    "placeholder_title",
    [
        "Match 1",
        "Match 2",
        "Match 17",
        "match-1",
        "match-2",
        "match-17",
        "match_1",
        "Match #1",
        "Fixture 1",
        "fixture-2",
        "Match",
        "Fixture",
        "",
        "   ",
        None,
    ],
)
def test_placeholder_title_detection(placeholder_title):
    """Placeholder titles match regex and are detected as non-semantic placeholders."""
    assert ChangeClassifier.is_placeholder_title(placeholder_title) is True


@pytest.mark.parametrize(
    "real_title",
    [
        "New South Wales vs Tasmania",
        "Queensland vs Western Australia",
        "Thailand vs Qatar",
        "Final: India vs Australia",
        "Match of the Day: WAU vs QUN",
    ],
)
def test_real_titles_not_detected_as_placeholders(real_title):
    """Real match titles are not classified as placeholders."""
    assert ChangeClassifier.is_placeholder_title(real_title) is False


def test_classifier_suppresses_placeholder_title_transition():
    """Classifier returns None when old title was a placeholder (initial enrichment)."""
    res = ChangeClassifier.classify_field_change(
        entity_type="MATCH",
        field_name="title",
        old_value="Match 2",
        new_value="New South Wales vs Tasmania",
    )
    assert res is None


def test_classifier_allows_genuine_title_change():
    """Classifier returns meaningful UPDATED when title changes between two genuine names."""
    res = ChangeClassifier.classify_field_change(
        entity_type="MATCH",
        field_name="title",
        old_value="India vs Australia",
        new_value="India vs South Africa",
    )
    assert res is not None
    assert res[0] == ChangeType.UPDATED.value
    assert res[1] == Severity.IMPORTANT.value


def test_policy_suppresses_placeholder_title_event():
    """NotificationPolicy filters out title events where old_value was a placeholder."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=2,
        external_id="4249663",
        change_type="UPDATED",
        field_name="title",
        old_value="Match 2",
        new_value="New South Wales vs Tasmania",
        severity="IMPORTANT",
    )
    assert NotificationPolicy.is_notifiable(event) is False


def test_policy_allows_genuine_title_change_event():
    """NotificationPolicy allows title events where old_value was a genuine name."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=2,
        external_id="4249663",
        change_type="UPDATED",
        field_name="title",
        old_value="India vs Australia",
        new_value="India vs South Africa",
        severity="IMPORTANT",
    )
    assert NotificationPolicy.is_notifiable(event) is True


# =============================================================================
# 2. Unverified Status Transition Handling (LIVE -> UNKNOWN)
# =============================================================================

def test_unverified_status_transition_generates_status_verification_card():
    """Status transition from LIVE to UNKNOWN is rendered as STATUS VERIFICATION with warning banner."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=17,
        external_id="4249664",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="LIVE",
        new_value="UNKNOWN",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        severity="IMPORTANT",
        metadata_json={"title": "Queensland vs Western Australia", "sport": "Cricket", "tour": "Sheffield Shield 2026-27"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=300)
    assert batch is not None

    # Subject check
    subject = NotificationRenderer.generate_subject(batch)
    assert "Status Verification" in subject or "Verification" in subject
    assert "Queensland vs Western Australia" in subject

    # HTML rendering check
    html_out = NotificationRenderer.render_html(batch)
    assert "UPDATE 01 &bull; STATUS VERIFICATION" in html_out
    assert "VERIFICATION NEEDED" in html_out
    assert "Queensland vs Western Australia" in html_out
    assert "Status Note:" in html_out
    assert "The latest scrape did not establish the current status" in html_out
    assert "Verify this match on FanCode &rarr;" in html_out or "Verify this match on FanCode" in html_out
    assert "https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info" in html_out

    # Executive Summary check
    assert "1 match status requires verification: Queensland vs Western Australia" in html_out

    # Plain-text rendering check
    text_out = NotificationRenderer.render_text(batch)
    assert "UPDATE 01 — STATUS VERIFICATION: Queensland vs Western Australia" in text_out
    assert "Status: LIVE -> UNKNOWN (unverified)" in text_out
    assert "The latest scrape did not establish the current status" in text_out
    assert "SOURCE LINK (Verify this match on FanCode →):" in text_out


# =============================================================================
# 3. Single Match LIVE Alert
# =============================================================================

def test_single_match_live_renders_numbered_card_and_live_badge():
    """Single match going LIVE renders red live badge, why it matters, and direct view link."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=1,
        external_id="4249663",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="LIVE",
        source_url="https://www.fancode.com/matches/tasmania-vs-new-south-wales-4249663/live-match-info",
        severity="CRITICAL",
        metadata_json={"title": "Tasmania vs New South Wales", "sport": "Cricket"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=301)
    assert batch is not None

    subject = NotificationRenderer.generate_subject(batch)
    assert "🔴 LIVE: Tasmania vs New South Wales" in subject

    html_out = NotificationRenderer.render_html(batch)
    assert "UPDATE 01 &bull; MATCH LIVE" in html_out
    assert "🔴 LIVE NOW" in html_out
    assert "Tasmania vs New South Wales" in html_out
    assert "The match is currently in progress and streaming live on FanCode." in html_out
    assert "View this match on FanCode" in html_out

    text_out = NotificationRenderer.render_text(batch)
    assert "UPDATE 01 — MATCH LIVE: Tasmania vs New South Wales" in text_out
    assert "🔴 LIVE" in text_out
    assert "The match is currently in progress and streaming live on FanCode." in text_out


# =============================================================================
# 4. Multi-Update Batch with Distinct Cards and Individual Links
# =============================================================================

def test_multi_update_batch_renders_distinct_numbered_cards_and_individual_links():
    """Batch with 3 distinct entities generates UPDATE 01, UPDATE 02, UPDATE 03 with 3 unique source links."""
    event1 = ChangeEvent(
        entity_type="match",
        entity_id=1,
        external_id="4249663",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="LIVE",
        new_value="UNKNOWN",
        source_url="https://www.fancode.com/matches/tasmania-vs-nsw-4249663/live",
        severity="IMPORTANT",
        metadata_json={"title": "Tasmania vs New South Wales", "sport": "Cricket"},
    )
    event2 = ChangeEvent(
        entity_type="match",
        entity_id=2,
        external_id="4249721",
        change_type="UPDATED",
        field_name="start_time",
        old_value="09:00 UTC",
        new_value="10:30 UTC",
        source_url="https://www.fancode.com/matches/thailand-vs-qatar-4249721/live",
        severity="IMPORTANT",
        metadata_json={"title": "Thailand vs Qatar", "sport": "Cricket"},
    )
    event3 = ChangeEvent(
        entity_type="video",
        entity_id=3,
        external_id="video-999",
        change_type="CREATED",
        field_name=None,
        old_value=None,
        new_value="Day 1 Highlights: TAS vs NSW",
        source_url="https://www.fancode.com/video/day-1-highlights-tas-vs-nsw-999",
        severity="INFO",
        metadata_json={"title": "Day 1 Highlights: TAS vs NSW", "sport": "Cricket"},
    )

    batch = EventGrouper.create_batch([event1, event2, event3], scrape_run_id=302)
    assert batch is not None
    assert len(batch.grouped_entities) == 3

    html_out = NotificationRenderer.render_html(batch)
    assert "UPDATE 01" in html_out
    assert "UPDATE 02" in html_out
    assert "UPDATE 03" in html_out

    # Verify each distinct source link is present
    assert "https://www.fancode.com/matches/tasmania-vs-nsw-4249663/live" in html_out
    assert "https://www.fancode.com/matches/thailand-vs-qatar-4249721/live" in html_out
    assert "https://www.fancode.com/video/day-1-highlights-tas-vs-nsw-999" in html_out

    # Verify context-aware button labels
    assert "Verify this match on FanCode" in html_out
    assert "View this match on FanCode" in html_out
    assert "Watch this video on FanCode" in html_out

    # Verify Executive Summary has 3 distinct categorized bullets
    assert "1 match status requires verification: Tasmania vs New South Wales" in html_out
    assert "1 match schedule updated: Thailand vs Qatar" in html_out
    assert "1 new video discovered: Day 1 Highlights: TAS vs NSW" in html_out

    # Plain-text verification
    text_out = NotificationRenderer.render_text(batch)
    assert "UPDATE 01 — STATUS VERIFICATION" in text_out
    assert "UPDATE 02 — MATCH SCHEDULE" in text_out
    assert "UPDATE 03 — NEW VIDEO" in text_out


# =============================================================================
# 5. Missing / Invalid URL Fallback Safety
# =============================================================================

def test_missing_or_invalid_url_renders_fallback_without_broken_link():
    """Missing, empty, or non-URL source_url renders 'Source link unavailable' safely without broken HTML links."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=5,
        external_id="4250000",
        change_type="UPDATED",
        field_name="venue",
        old_value="Old Stadium",
        new_value="New Arena",
        source_url=None,  # Missing URL
        severity="IMPORTANT",
        metadata_json={"title": "Team Alpha vs Team Beta"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=303)
    assert batch is not None

    html_out = NotificationRenderer.render_html(batch)
    assert "Source link unavailable" in html_out
    assert '<a href="None"' not in html_out
    assert '<a href=""' not in html_out

    text_out = NotificationRenderer.render_text(batch)
    assert "Source link unavailable" in text_out


def test_relative_url_is_normalized_to_full_fancode_url():
    """Relative URLs starting with / are automatically prefixed with https://www.fancode.com."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=6,
        external_id="4250001",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="LIVE",
        source_url="/matches/team-c-vs-team-d-4250001/live",
        severity="CRITICAL",
        metadata_json={"title": "Team C vs Team D"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=304)
    assert batch is not None

    html_out = NotificationRenderer.render_html(batch)
    assert 'href="https://www.fancode.com/matches/team-c-vs-team-d-4250001/live"' in html_out

    text_out = NotificationRenderer.render_text(batch)
    assert "https://www.fancode.com/matches/team-c-vs-team-d-4250001/live" in text_out


# =============================================================================
# 6. Strict HTML Escaping & Injection Safety
# =============================================================================

def test_strict_html_escaping_prevents_xss_injection():
    """Dynamic fields with malicious HTML / XSS payloads are strictly escaped."""
    malicious_title = "<script>alert('xss')</script> & <b>bold</b>"
    malicious_val = "<img src=x onerror=alert(1)>"

    event = ChangeEvent(
        entity_type="match",
        entity_id=7,
        external_id="4250002",
        change_type="UPDATED",
        field_name="venue",
        old_value="Safe Venue",
        new_value=malicious_val,
        source_url="https://www.fancode.com/matches/test",
        severity="IMPORTANT",
        metadata_json={"title": malicious_title},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=305)
    assert batch is not None

    html_out = NotificationRenderer.render_html(batch)
    assert "<script>" not in html_out
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;" in html_out
    assert "<img src=x" not in html_out
    assert "&lt;img src=x" in html_out


# =============================================================================
# 7. Cancelled & Postponed Fixtures
# =============================================================================

def test_cancelled_match_renders_critical_subject_and_rationale():
    """Cancelled match produces warning subject, badge, and clear cancellation explanation."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=8,
        external_id="4250003",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="CANCELLED",
        source_url="https://www.fancode.com/matches/cancelled-match-4250003",
        severity="CRITICAL",
        metadata_json={"title": "England vs New Zealand"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=306)
    assert batch is not None

    subject = NotificationRenderer.generate_subject(batch)
    assert "⚠️ CANCELLED: England vs New Zealand" in subject

    html_out = NotificationRenderer.render_html(batch)
    assert "UPDATE 01 &bull; MATCH CANCELLED" in html_out
    assert "⚠️ CANCELLED" in html_out
    assert "The fixture was officially marked as cancelled on FanCode." in html_out


def test_postponed_match_renders_postponed_card():
    """Postponed match produces postponed badge and clear delay explanation."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=9,
        external_id="4250004",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="SCHEDULED",
        new_value="POSTPONED",
        source_url="https://www.fancode.com/matches/postponed-match-4250004",
        severity="IMPORTANT",
        metadata_json={"title": "South Africa vs Pakistan"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=307)
    assert batch is not None

    html_out = NotificationRenderer.render_html(batch)
    assert "UPDATE 01 &bull; MATCH POSTPONED" in html_out
    assert "POSTPONED" in html_out
    assert "The scheduled match timing has been postponed or delayed." in html_out


# =============================================================================
# 8. EmailMessage Construction & Recipient Configuration
# =============================================================================

def test_build_email_message_constructs_complete_object():
    """build_email_message populates subject, html_body, text_body, from_addr, and to_addrs."""
    event = ChangeEvent(
        entity_type="match",
        entity_id=10,
        external_id="4250005",
        change_type="CREATED",
        field_name=None,
        old_value=None,
        new_value="Sri Lanka vs West Indies",
        source_url="https://www.fancode.com/matches/sl-vs-wi-4250005",
        severity="IMPORTANT",
        metadata_json={"title": "Sri Lanka vs West Indies"},
    )

    batch = EventGrouper.create_batch([event], scrape_run_id=308)
    recipients = EmailRecipientConfig(
        from_addr="alerts@fancode-monitor.local",
        to_addrs=["ops@example.com"],
        cc_addrs=["manager@example.com"],
    )

    msg = NotificationRenderer.build_email_message(batch, recipients)
    assert msg.subject == "FanCode Monitor — New Match: Sri Lanka vs West Indies"
    assert msg.from_addr == "alerts@fancode-monitor.local"
    assert msg.to_addrs == ["ops@example.com"]
    assert msg.cc_addrs == ["manager@example.com"]
    assert "Sri Lanka vs West Indies" in msg.html_body
    assert "Sri Lanka vs West Indies" in msg.text_body
