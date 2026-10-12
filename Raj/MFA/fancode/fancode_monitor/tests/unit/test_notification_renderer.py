"""
test_notification_renderer.py – Unit tests for Phase 9 NotificationRenderer (HTML, text, sanitization).
"""

from __future__ import annotations

import pytest
from app.change_detection.models import ChangeType, EntityType, ProposedChangeEvent, Severity
from app.notifications.grouping import EventGrouper
from app.notifications.models import EmailRecipientConfig
from app.notifications.renderer import NotificationRenderer


class TestNotificationRenderer:
    def test_subject_for_critical_match_live(self):
        ev = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
            metadata={"title": "India vs Australia"},
        )
        batch = EventGrouper.create_batch([ev])
        subject = NotificationRenderer.generate_subject(batch)
        assert subject == "FanCode Monitor — 🔴 LIVE: India vs Australia"

    def test_subject_for_critical_match_cancelled(self):
        ev = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="CANCELLED",
            severity=Severity.CRITICAL.value,
            metadata={"title": "Arsenal vs Chelsea"},
        )
        batch = EventGrouper.create_batch([ev])
        subject = NotificationRenderer.generate_subject(batch)
        assert subject == "FanCode Monitor — ⚠️ CANCELLED: Arsenal vs Chelsea"

    def test_html_rendering_and_sanitization(self):
        malicious_title = "<script>alert('xss')</script> MI vs CSK"
        ev = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.CREATED.value,
            new_value=malicious_title,
            severity=Severity.IMPORTANT.value,
            source_url="https://www.fancode.com/match/101",
        )
        batch = EventGrouper.create_batch([ev])
        html = NotificationRenderer.render_html(batch)

        # Must not contain unescaped script tag
        assert "<script>alert('xss')</script>" not in html
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html or "&lt;script&gt;" in html
        # Must contain valid structure and link
        assert "FanCode Monitor Alert" in html
        assert "https://www.fancode.com/match/101" in html

    def test_plain_text_rendering(self):
        ev1 = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.STATUS_CHANGED.value,
            field_name="status",
            old_value="UPCOMING",
            new_value="LIVE",
            severity=Severity.CRITICAL.value,
            source_url="https://www.fancode.com/match/101",
        )
        ev2 = ProposedChangeEvent(
            entity_type=EntityType.VIDEO.value,
            entity_id=201,
            change_type=ChangeType.CREATED.value,
            new_value="Match Highlights",
            severity=Severity.INFO.value,
            source_url="https://www.fancode.com/video/201",
        )
        batch = EventGrouper.create_batch([ev1, ev2])
        text = NotificationRenderer.render_text(batch)

        assert "Status changed: UPCOMING -> LIVE" in text
        assert "CREATED (Severity: INFO)" in text
        assert "https://www.fancode.com/match/101" in text
        assert "https://www.fancode.com/video/201" in text

    def test_build_email_message(self):
        ev = ProposedChangeEvent(
            entity_type=EntityType.MATCH.value,
            entity_id=101,
            change_type=ChangeType.CREATED.value,
            new_value="Test Match",
            severity=Severity.IMPORTANT.value,
        )
        batch = EventGrouper.create_batch([ev])
        recipients = EmailRecipientConfig(
            from_addr="alerts@fancode.local",
            to_addrs=["dev@fancode.local"],
            cc_addrs=["lead@fancode.local"],
        )
        msg = NotificationRenderer.build_email_message(batch, recipients)

        assert msg.from_addr == "alerts@fancode.local"
        assert msg.to_addrs == ["dev@fancode.local"]
        assert msg.cc_addrs == ["lead@fancode.local"]
        assert len(msg.html_body) > 0
        assert len(msg.text_body) > 0
