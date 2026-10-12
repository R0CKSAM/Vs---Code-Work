"""
renderer.py – Deterministic, sanitized HTML and plain-text email rendering for FanCode.
Upgraded to provide structured executive summaries, sequentially numbered cards,
entity-specific verified source links, 'What changed?' / 'Why it matters' rationales,
and safe handling for unverified status transitions.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.change_detection.models import ChangeType, EntityType, Severity
from app.notifications.models import (
    EmailMessage,
    EmailRecipientConfig,
    GroupedEntity,
    NotificationBatchDraft,
)

logger = logging.getLogger(__name__)


class NotificationRenderer:
    """
    Renders deterministic, email-client safe HTML and plain-text digests.
    All scraped text is strictly HTML-escaped to prevent injection.
    """

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    @classmethod
    def generate_subject(cls, batch: NotificationBatchDraft) -> str:
        """Return an RFC-friendly subject capped at 78 Unicode characters."""
        subject = cls._generate_subject_unbounded(batch)
        if len(subject) <= 78:
            return subject
        return subject[:77].rstrip() + "…"

    @classmethod
    def _generate_subject_unbounded(cls, batch: NotificationBatchDraft) -> str:
        """
        Generates a deterministic, human-readable email subject.
        Highlights CRITICAL events, unverified status checks, and specific entity titles.
        """
        if not batch.events:
            return "FanCode Monitor — No changes"

        total_events = len(batch.events)

        # 1. Check for LIVE matches (CRITICAL)
        live_events = [
            e for e in batch.events
            if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() == "LIVE"
        ]
        if live_events:
            first_live = live_events[0]
            matched_entity = next(
                (g for g in batch.grouped_entities if any(ge is first_live for ge in g.events)),
                None,
            )
            title = matched_entity.title if matched_entity and matched_entity.title else None
            if title:
                other_count = total_events - 1
                if other_count > 0:
                    return f"FanCode Monitor — 🔴 LIVE: {title} (+{other_count} other change{'s' if other_count > 1 else ''})"
                return f"FanCode Monitor — 🔴 LIVE: {title}"
            return f"FanCode Monitor — 🔴 Match is now LIVE ({total_events} change{'s' if total_events > 1 else ''})"

        # 2. Check for CANCELLED / ABANDONED matches (CRITICAL)
        cancelled_events = [
            e for e in batch.events
            if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() in ("CANCELLED", "ABANDONED")
        ]
        if cancelled_events:
            first_cancel = cancelled_events[0]
            matched_entity = next(
                (g for g in batch.grouped_entities if any(ge is first_cancel for ge in g.events)),
                None,
            )
            title = matched_entity.title if matched_entity and matched_entity.title else None
            status_val = (getattr(first_cancel, "new_value", "") or "CANCELLED").upper()
            if title:
                other_count = total_events - 1
                if other_count > 0:
                    return f"FanCode Monitor — ⚠️ {status_val}: {title} (+{other_count} other change{'s' if other_count > 1 else ''})"
                return f"FanCode Monitor — ⚠️ {status_val}: {title}"
            return f"FanCode Monitor — ⚠️ Match {status_val.title()} ({total_events} change{'s' if total_events > 1 else ''})"

        # 3. Check for UNVERIFIED status transitions (e.g. LIVE -> UNKNOWN)
        unverified_events = [
            e for e in batch.events if cls._is_unverified_status_event(e)
        ]
        if unverified_events:
            first_unverified = unverified_events[0]
            matched_entity = next(
                (g for g in batch.grouped_entities if any(ge is first_unverified for ge in g.events)),
                None,
            )
            title = matched_entity.title if matched_entity and matched_entity.title else None
            if title:
                other_count = total_events - 1
                if other_count > 0:
                    return f"FanCode Monitor — ⚠️ Status Verification: {title} (+{other_count} other change{'s' if other_count > 1 else ''})"
                return f"FanCode Monitor — ⚠️ Status Verification: {title}"
            return f"FanCode Monitor — ⚠️ Status Verification Needed ({total_events} change{'s' if total_events > 1 else ''})"

        # 4. If single grouped entity, provide precise headline
        if len(batch.grouped_entities) == 1:
            entity = batch.grouped_entities[0]
            e_title = entity.title or f"{entity.entity_type} #{entity.entity_id}"
            if len(entity.events) == 1:
                ev = entity.events[0]
                c_type = getattr(ev, "change_type", "")
                f_name = getattr(ev, "field_name", "")
                n_val = getattr(ev, "new_value", "")
                if c_type == ChangeType.CREATED.value:
                    if entity.entity_type == EntityType.VIDEO.value:
                        return f"FanCode Monitor — New Video: {e_title}"
                    elif entity.entity_type == EntityType.TOUR.value:
                        return f"FanCode Monitor — New Tournament: {e_title}"
                    return f"FanCode Monitor — New {entity.entity_type.title()}: {e_title}"
                elif c_type == ChangeType.STATUS_CHANGED.value:
                    return f"FanCode Monitor — Status Update ({n_val}): {e_title}"
                elif f_name == "venue":
                    return f"FanCode Monitor — Venue Changed: {e_title}"
                elif f_name in ("start_time", "match_date"):
                    return f"FanCode Monitor — Schedule Changed: {e_title}"
                elif f_name in ("team_a_name", "team_b_name"):
                    return f"FanCode Monitor — Lineup Updated: {e_title}"
                else:
                    return f"FanCode Monitor — Update: {e_title}"
            else:
                return f"FanCode Monitor — {len(entity.events)} Updates: {e_title}"

        # 5. Multi-entity digest
        has_critical = any(getattr(e, "severity", "") == Severity.CRITICAL.value for e in batch.events)
        has_important = any(getattr(e, "severity", "") == Severity.IMPORTANT.value for e in batch.events)

        if has_critical:
            return f"FanCode Monitor — 🔴 {total_events} Meaningful Changes Detected"
        if has_important:
            return f"FanCode Monitor — {total_events} Important Changes Detected"

        return f"FanCode Monitor — {total_events} Meaningful Change{'s' if total_events > 1 else ''} Detected"

    @classmethod
    def render_html(cls, batch: NotificationBatchDraft) -> str:
        """
        Renders a clean, responsive, table-based HTML email body.
        Guaranteed zero JavaScript and strict HTML sanitization.
        """
        subject = cls.generate_subject(batch)
        escaped_subject = html.escape(subject)
        total_events = len(batch.events)
        total_entities = len(batch.grouped_entities)

        # Build executive summary bullets
        summary_bullets = cls._generate_executive_summary_items(batch)
        summary_items_html = "\n".join(
            f'<li style="margin-bottom: 6px; color: #334155;">{html.escape(bullet)}</li>'
            for bullet in summary_bullets
        )

        # Build numbered entity cards
        cards_html: List[str] = []
        for idx, g in enumerate(batch.grouped_entities, start=1):
            cards_html.append(cls._render_entity_card_html(idx, g))

        cards_combined = "\n".join(cards_html)

        # Current formatted UTC timestamp
        timestamp_str = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_subject}</title>
</head>
<body style="margin: 0; padding: 24px 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center">
        <div class="container" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
          <!-- Header -->
          <div class="header" style="background-color: #0f172a; color: #ffffff; padding: 24px; text-align: left;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <h1 style="margin: 0; font-size: 20px; font-weight: 700; color: #ffffff;">FanCode Monitor Alert</h1>
                  <p style="margin: 4px 0 0 0; font-size: 13px; color: #94a3b8;">Automated Match &amp; Content Updates</p>
                </td>
                <td align="right" style="vertical-align: top;">
                  <span style="display: inline-block; padding: 4px 8px; background-color: #1e293b; color: #cbd5e1; border-radius: 4px; font-size: 11px; font-weight: 600;">
                    {total_events} Change{'s' if total_events != 1 else ''} &bull; {total_entities} Entit{'ies' if total_entities != 1 else 'y'}
                  </span>
                </td>
              </tr>
            </table>
          </div>

          <!-- Executive Summary -->
          <div class="summary-box" style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 18px 24px;">
            <div style="font-size: 13px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">
              Executive Summary
            </div>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.6;">
              {summary_items_html}
            </ul>
          </div>

          <!-- Numbered Cards Content -->
          <div class="content" style="padding: 20px 24px;">
            {cards_combined}
          </div>

          <!-- Footer -->
          <div class="footer" style="background-color: #f8fafc; padding: 16px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
            FanCode Public-Site Monitor &bull; Automated notification generated at {timestamp_str}
          </div>
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""
        return html_template

    @classmethod
    def render_text(cls, batch: NotificationBatchDraft) -> str:
        """
        Renders clean, structured plain-text fallback content.
        """
        subject = cls.generate_subject(batch)
        timestamp_str = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )
        summary_bullets = cls._generate_executive_summary_items(batch)

        lines: List[str] = [
            "=" * 60,
            "FANCODE MONITOR ALERT",
            "=" * 60,
            f"Subject: {subject}",
            f"Generated: {timestamp_str}",
            f"Total Changes: {len(batch.events)} across {len(batch.grouped_entities)} entities",
            "",
            "--- EXECUTIVE SUMMARY ---",
        ]

        for bullet in summary_bullets:
            lines.append(f"  * {bullet}")
        lines.append("")

        for idx, g in enumerate(batch.grouped_entities, start=1):
            meta = cls._get_entity_card_meta(g)
            card_num = f"UPDATE {idx:02d}"
            card_cat = meta["category_name"]
            e_title = g.title or f"{g.entity_type} #{g.entity_id}"
            valid_url = cls._validate_source_url(g.source_url)

            lines.append("-" * 60)
            lines.append(f"{card_num} — {card_cat}: {e_title}")
            lines.append(f"[{g.entity_type.upper()}] {e_title}")
            lines.append("-" * 60)

            context_parts = []
            if g.external_id:
                context_parts.append(f"External ID: {g.external_id}")
            if g.sport_name:
                context_parts.append(f"Sport: {g.sport_name}")
            if g.tour_name:
                context_parts.append(f"Tournament: {g.tour_name}")
            if context_parts:
                lines.append(f"Context: {' | '.join(context_parts)}")

            lines.append("")
            lines.append("WHAT CHANGED?")
            for item in meta["what_changed_items"]:
                label, old_val, new_val = item
                if old_val:
                    lines.append(f"  * {label}: {old_val} -> {new_val}")
                else:
                    lines.append(f"  * {label}: {new_val}")

            # Keep a concise, machine-scannable event line in the text part.
            # This mirrors information shown visually in the HTML card.
            for event in g.events:
                change_type = str(getattr(event, "change_type", "UPDATE") or "UPDATE")
                severity = str(getattr(event, "severity", "INFO") or "INFO")
                field_name = getattr(event, "field_name", None)
                old_value = getattr(event, "old_value", None)
                new_value = getattr(event, "new_value", None)
                if field_name and old_value is not None:
                    label = str(field_name).replace("_", " ").title()
                    lines.append(
                        f"  {label} changed: {old_value} -> {new_value} "
                        f"(Severity: {severity})"
                    )
                else:
                    lines.append(f"  {change_type} (Severity: {severity})")

            lines.append("")
            lines.append("WHY IT MATTERS:")
            lines.append(f"  {meta['why_it_matters']}")

            lines.append("")
            if valid_url:
                lines.append(f"SOURCE LINK ({meta['link_label']}):")
                lines.append(f"  {valid_url}")
                lines.append(f"Link: {valid_url}")
            else:
                lines.append("SOURCE LINK:")
                lines.append("  Source link unavailable")

            lines.append("")

        lines.append("=" * 60)
        lines.append("FanCode Public-Site Monitor — Automated notification")
        lines.append("=" * 60)
        return "\n".join(lines)

    @classmethod
    def build_email_message(
        cls,
        batch: NotificationBatchDraft,
        recipients: EmailRecipientConfig,
    ) -> EmailMessage:
        """
        Constructs a complete EmailMessage object with rendered HTML, plain-text, and subject.
        """
        subject = cls.generate_subject(batch)
        html_body = cls.render_html(batch)
        text_body = cls.render_text(batch)

        return EmailMessage(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_addr=recipients.from_addr,
            to_addrs=recipients.to_addrs,
            cc_addrs=recipients.cc_addrs,
            bcc_addrs=recipients.bcc_addrs,
        )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _is_unverified_status_event(cls, e: Any) -> bool:
        """Determines whether an event represents an unverified status transition (e.g. LIVE -> UNKNOWN)."""
        f_name = getattr(e, "field_name", "")
        c_type = getattr(e, "change_type", "")
        new_v = (getattr(e, "new_value", "") or "").upper()
        old_v = (getattr(e, "old_value", "") or "").upper()

        if f_name == "status" or c_type == ChangeType.STATUS_CHANGED.value:
            if new_v in ("UNKNOWN", "", "NONE", "UNCONFIRMED", "UNVERIFIED", "NULL"):
                return True
        return False

    @classmethod
    def _validate_source_url(cls, url: Optional[str]) -> Optional[str]:
        """Validates and canonicalizes source URLs. Never invents fake links."""
        if not url or not isinstance(url, str):
            return None
        cleaned = url.strip()
        if not cleaned:
            return None
        if cleaned.startswith("/"):
            cleaned = "https://www.fancode.com" + cleaned
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            parsed = urlparse(cleaned)
            host = (parsed.hostname or "").lower()
            if host == "fancode.com" or host.endswith(".fancode.com"):
                return cleaned
        return None

    @staticmethod
    def _format_schedule_value(value: str) -> str:
        """Render ISO timestamps in IST while preserving non-date labels."""
        if not value:
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
        except (TypeError, ValueError):
            return value

    @classmethod
    def _get_entity_card_meta(cls, g: GroupedEntity) -> Dict[str, Any]:
        """
        Extracts categorization, badges, what-changed breakdowns, and plain-English rationales.
        """
        e_type = g.entity_type.upper()
        has_unverified = any(cls._is_unverified_status_event(e) for e in g.events)

        # 1. Determine Category, Badge, and Action Link Label
        live_event = next((e for e in g.events if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() == "LIVE"), None)
        cancel_event = next((e for e in g.events if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() in ("CANCELLED", "ABANDONED")), None)
        postpone_event = next((e for e in g.events if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() in ("POSTPONED", "DELAYED")), None)
        completed_event = next((e for e in g.events if getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() == "COMPLETED"), None)
        created_event = next((e for e in g.events if getattr(e, "change_type", "") == ChangeType.CREATED.value), None)
        removed_event = next((e for e in g.events if getattr(e, "change_type", "") == ChangeType.REMOVED.value), None)
        schedule_event = next((e for e in g.events if getattr(e, "field_name", "") in ("start_time", "match_date")), None)
        venue_event = next((e for e in g.events if getattr(e, "field_name", "") == "venue"), None)
        lineup_event = next((e for e in g.events if getattr(e, "field_name", "") in ("team_a_name", "team_b_name")), None)

        if has_unverified:
            category_name = "STATUS VERIFICATION"
            badge_text = "VERIFICATION NEEDED"
            badge_bg = "#fef3c7"
            badge_color = "#92400e"
            accent_color = "#f59e0b"
            link_label = "Verify this match on FanCode →"
            why_it_matters = (
                "The latest scrape did not establish the current status. "
                "This may be a temporary data issue and does not confirm that the match has stopped."
            )
        elif live_event:
            category_name = "MATCH LIVE"
            badge_text = "🔴 LIVE NOW"
            badge_bg = "#fee2e2"
            badge_color = "#991b1b"
            accent_color = "#ef4444"
            link_label = "View on FanCode →"
            why_it_matters = "The match is currently in progress and streaming live on FanCode."
        elif cancel_event:
            status_str = (getattr(cancel_event, "new_value", "") or "CANCELLED").upper()
            category_name = f"MATCH {status_str}"
            badge_text = f"⚠️ {status_str}"
            badge_bg = "#fee2e2"
            badge_color = "#991b1b"
            accent_color = "#ef4444"
            link_label = "View this match on FanCode →"
            why_it_matters = f"The fixture was officially marked as {status_str.lower()} on FanCode."
        elif postpone_event:
            category_name = "MATCH POSTPONED"
            badge_text = "POSTPONED"
            badge_bg = "#fef3c7"
            badge_color = "#92400e"
            accent_color = "#f59e0b"
            link_label = "View this match on FanCode →"
            why_it_matters = "The scheduled match timing has been postponed or delayed."
        elif completed_event:
            category_name = "MATCH COMPLETED"
            badge_text = "COMPLETED"
            badge_bg = "#dcfce7"
            badge_color = "#166534"
            accent_color = "#22c55e"
            link_label = "View this match on FanCode →"
            why_it_matters = "The match has concluded and coverage is finished."
        elif created_event:
            if e_type == EntityType.VIDEO.value:
                category_name = "NEW VIDEO"
                badge_text = "NEW VIDEO"
                badge_bg = "#ede9fe"
                badge_color = "#5b21b6"
                accent_color = "#8b5cf6"
                link_label = "Watch this video on FanCode →"
                why_it_matters = "New on-demand video highlights or replay published on FanCode."
            elif e_type == EntityType.TOUR.value:
                category_name = "NEW TOURNAMENT"
                badge_text = "NEW TOURNAMENT"
                badge_bg = "#dbeafe"
                badge_color = "#1e40af"
                accent_color = "#3b82f6"
                link_label = "View on FanCode →"
                why_it_matters = "A new tournament or series has been announced on FanCode."
            elif e_type == EntityType.SPORT.value:
                category_name = "NEW SPORT"
                badge_text = "NEW SPORT"
                badge_bg = "#dbeafe"
                badge_color = "#1e40af"
                accent_color = "#3b82f6"
                link_label = "View on FanCode →"
                why_it_matters = "A new sports category has been introduced on FanCode."
            else:
                category_name = "NEW MATCH"
                badge_text = "NEW FIXTURE"
                badge_bg = "#dbeafe"
                badge_color = "#1e40af"
                accent_color = "#3b82f6"
                link_label = "View this match on FanCode →"
                why_it_matters = "A new fixture has been added to the FanCode broadcast schedule."
        elif removed_event:
            category_name = f"{e_type} REMOVED"
            badge_text = "REMOVED"
            badge_bg = "#fee2e2"
            badge_color = "#991b1b"
            accent_color = "#ef4444"
            link_label = "View on FanCode →"
            why_it_matters = "The entity is no longer listed on the authoritative FanCode schedule."
        elif schedule_event:
            category_name = "MATCH SCHEDULE"
            badge_text = "SCHEDULE UPDATED"
            badge_bg = "#e0f2fe"
            badge_color = "#0369a1"
            accent_color = "#0284c7"
            link_label = "View this match on FanCode →"
            why_it_matters = "The match start time or date has been updated on FanCode."
        elif venue_event:
            category_name = "VENUE CHANGED"
            badge_text = "VENUE UPDATED"
            badge_bg = "#e0f2fe"
            badge_color = "#0369a1"
            accent_color = "#0284c7"
            link_label = "View this match on FanCode →"
            why_it_matters = "The match venue or stadium location has been relocated."
        elif lineup_event:
            category_name = "TEAMS UPDATED"
            badge_text = "LINEUP UPDATED"
            badge_bg = "#dbeafe"
            badge_color = "#1e40af"
            accent_color = "#3b82f6"
            link_label = "View this match on FanCode →"
            why_it_matters = "The competing teams or participant names were modified."
        else:
            category_name = f"{e_type} UPDATE"
            badge_text = "UPDATED"
            badge_bg = "#f1f5f9"
            badge_color = "#475569"
            accent_color = "#64748b"
            link_label = "Watch this video on FanCode →" if e_type == EntityType.VIDEO.value else "View on FanCode →"
            why_it_matters = "Key fixture or content metadata was updated on FanCode."

        # 2. Build 'What Changed' item list: (label, old_val, new_val)
        what_changed_items: List[Tuple[str, str, str]] = []
        for e in g.events:
            c_type = getattr(e, "change_type", "")
            f_name = getattr(e, "field_name", "")
            old_v = str(getattr(e, "old_value", "") or "")
            new_v = str(getattr(e, "new_value", "") or "")

            if c_type == ChangeType.CREATED.value:
                what_changed_items.append(("Event", "", f"New {g.entity_type.title()} Discovered"))
            elif c_type == ChangeType.REMOVED.value:
                what_changed_items.append(("Event", "Listed", "Removed from schedule"))
            elif c_type == ChangeType.STATUS_CHANGED.value or f_name == "status":
                if new_v.upper() in ("UNKNOWN", "", "NONE", "UNCONFIRMED", "UNVERIFIED", "NULL"):
                    what_changed_items.append(("Status", old_v or "LIVE", "UNKNOWN (unverified)"))
                elif new_v.upper() == "LIVE":
                    what_changed_items.append(("Status", old_v or "SCHEDULED", "🔴 LIVE"))
                else:
                    what_changed_items.append(("Status", old_v or "UNKNOWN", new_v))
            elif f_name == "venue":
                what_changed_items.append(("Venue", old_v or "Not specified", new_v))
            elif f_name in ("start_time", "match_date"):
                what_changed_items.append((
                    "Schedule",
                    cls._format_schedule_value(old_v) if old_v else "Not specified",
                    cls._format_schedule_value(new_v),
                ))
            elif f_name == "team_a_name":
                what_changed_items.append(("Team A", old_v or "Not specified", new_v))
            elif f_name == "team_b_name":
                what_changed_items.append(("Team B", old_v or "Not specified", new_v))
            elif f_name == "title":
                what_changed_items.append(("Title", old_v or "Not specified", new_v))
            elif f_name:
                what_changed_items.append((f_name.replace("_", " ").title(), old_v or "None", new_v))
            else:
                what_changed_items.append(("Update", old_v, new_v))

        return {
            "category_name": category_name,
            "badge_text": badge_text,
            "badge_bg": badge_bg,
            "badge_color": badge_color,
            "accent_color": accent_color,
            "link_label": link_label,
            "why_it_matters": why_it_matters,
            "what_changed_items": what_changed_items,
            "has_unverified": has_unverified,
        }

    @classmethod
    def _generate_executive_summary_items(cls, batch: NotificationBatchDraft) -> List[str]:
        """
        Constructs concise, plain-English summary bullet points categorizing all updates.
        """
        bullets: List[str] = []

        # Count occurrences of categories across entities
        unverified_entities = []
        live_entities = []
        cancelled_entities = []
        postponed_entities = []
        schedule_entities = []
        venue_entities = []
        lineup_entities = []
        new_match_entities = []
        new_video_entities = []
        new_tour_entities = []
        other_entities = []

        for g in batch.grouped_entities:
            title = g.title or f"{g.entity_type} #{g.entity_id}"
            has_unverified = any(cls._is_unverified_status_event(e) for e in g.events)
            has_live = any(getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() == "LIVE" for e in g.events)
            has_cancel = any(getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() in ("CANCELLED", "ABANDONED") for e in g.events)
            has_postpone = any(getattr(e, "field_name", "") == "status" and (getattr(e, "new_value", "") or "").upper() in ("POSTPONED", "DELAYED") for e in g.events)
            has_created = any(getattr(e, "change_type", "") == ChangeType.CREATED.value for e in g.events)
            has_schedule = any(getattr(e, "field_name", "") in ("start_time", "match_date") for e in g.events)
            has_venue = any(getattr(e, "field_name", "") == "venue" for e in g.events)
            has_lineup = any(getattr(e, "field_name", "") in ("team_a_name", "team_b_name") for e in g.events)

            if has_unverified:
                unverified_entities.append(title)
            elif has_live:
                live_entities.append(title)
            elif has_cancel:
                cancelled_entities.append(title)
            elif has_postpone:
                postponed_entities.append(title)
            elif has_created:
                if g.entity_type == EntityType.VIDEO.value:
                    new_video_entities.append(title)
                elif g.entity_type == EntityType.TOUR.value:
                    new_tour_entities.append(title)
                else:
                    new_match_entities.append(title)
            elif has_schedule:
                schedule_entities.append(title)
            elif has_venue:
                venue_entities.append(title)
            elif has_lineup:
                lineup_entities.append(title)
            else:
                other_entities.append(title)

        if unverified_entities:
            if len(unverified_entities) == 1:
                bullets.append(f"1 match status requires verification: {unverified_entities[0]}")
            else:
                bullets.append(f"{len(unverified_entities)} match statuses require verification")

        if live_entities:
            if len(live_entities) == 1:
                bullets.append(f"1 match is now LIVE: {live_entities[0]}")
            else:
                bullets.append(f"{len(live_entities)} matches are now LIVE")

        if cancelled_entities:
            if len(cancelled_entities) == 1:
                bullets.append(f"1 match cancelled: {cancelled_entities[0]}")
            else:
                bullets.append(f"{len(cancelled_entities)} matches cancelled")

        if postponed_entities:
            if len(postponed_entities) == 1:
                bullets.append(f"1 match postponed: {postponed_entities[0]}")
            else:
                bullets.append(f"{len(postponed_entities)} matches postponed")

        if schedule_entities:
            if len(schedule_entities) == 1:
                bullets.append(f"1 match schedule updated: {schedule_entities[0]}")
            else:
                bullets.append(f"{len(schedule_entities)} match schedules updated")

        if venue_entities:
            if len(venue_entities) == 1:
                bullets.append(f"1 match venue changed: {venue_entities[0]}")
            else:
                bullets.append(f"{len(venue_entities)} match venues changed")

        if lineup_entities:
            if len(lineup_entities) == 1:
                bullets.append(f"1 lineup updated: {lineup_entities[0]}")
            else:
                bullets.append(f"{len(lineup_entities)} lineups updated")

        if new_match_entities:
            if len(new_match_entities) == 1:
                bullets.append(f"1 new fixture added: {new_match_entities[0]}")
            else:
                bullets.append(f"{len(new_match_entities)} new fixtures added")

        if new_video_entities:
            if len(new_video_entities) == 1:
                bullets.append(f"1 new video discovered: {new_video_entities[0]}")
            else:
                bullets.append(f"{len(new_video_entities)} new videos discovered")

        if new_tour_entities:
            if len(new_tour_entities) == 1:
                bullets.append(f"1 new tournament discovered: {new_tour_entities[0]}")
            else:
                bullets.append(f"{len(new_tour_entities)} new tournaments discovered")

        if other_entities:
            if len(other_entities) == 1:
                bullets.append(f"1 content update: {other_entities[0]}")
            else:
                bullets.append(f"{len(other_entities)} content updates")

        if not bullets:
            bullets.append(f"{len(batch.events)} meaningful updates detected")

        return bullets

    @classmethod
    def _render_entity_card_html(cls, idx: int, g: GroupedEntity) -> str:
        """Renders HTML for a single numbered update card."""
        meta = cls._get_entity_card_meta(g)
        card_num_str = f"UPDATE {idx:02d}"
        category_escaped = html.escape(meta["category_name"])
        title_escaped = html.escape(g.title or f"{g.entity_type} #{g.entity_id}")
        badge_text_escaped = html.escape(meta["badge_text"])
        why_it_matters_escaped = html.escape(meta["why_it_matters"])
        link_label_escaped = html.escape(meta["link_label"]).replace("→", "&rarr;")

        # Context row (Sport, Tournament, External ID)
        context_items: List[str] = []
        if g.external_id:
            context_items.append(f"<strong>ID:</strong> {html.escape(str(g.external_id))}")
        if g.sport_name:
            context_items.append(f"<strong>Sport:</strong> {html.escape(str(g.sport_name))}")
        if g.tour_name:
            context_items.append(f"<strong>Tournament:</strong> {html.escape(str(g.tour_name))}")

        context_html = ""
        if context_items:
            context_html = f"""
            <div style="font-size: 12px; color: #64748b; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #f1f5f9;">
              {' &bull; '.join(context_items)}
            </div>"""

        # Build 'What changed?' rows
        what_changed_rows: List[str] = []
        for label, old_val, new_val in meta["what_changed_items"]:
            label_esc = html.escape(label)
            old_esc = html.escape(old_val)
            new_esc = html.escape(new_val)

            if not old_val:
                val_html = f'<span style="color: #059669; font-weight: 600;">{new_esc}</span>'
            else:
                if "LIVE" in new_val:
                    new_styled = f'<span style="color: #dc2626; font-weight: 700;">{new_esc}</span>'
                elif "unverified" in new_val:
                    new_styled = f'<span style="color: #b45309; font-weight: 600;">{new_esc}</span>'
                else:
                    new_styled = f'<span style="color: #059669; font-weight: 600;">{new_esc}</span>'

                val_html = f'<span style="text-decoration: line-through; color: #94a3b8; margin-right: 6px;">{old_esc}</span> &rarr; {new_styled}'

            what_changed_rows.append(f"""
              <tr>
                <td style="width: 110px; font-weight: 600; color: #64748b; padding: 4px 0; vertical-align: top; font-size: 13px;">{label_esc}:</td>
                <td style="padding: 4px 0; vertical-align: top; font-size: 13px; color: #0f172a;">{val_html}</td>
              </tr>""")

        what_changed_table_html = f"""
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 4px;">
            {''.join(what_changed_rows)}
          </table>"""

        # Source link button / fallback
        valid_url = cls._validate_source_url(g.source_url)
        if valid_url:
            clean_url = html.escape(valid_url)
            btn_bg = meta["accent_color"]
            source_link_html = f"""
            <div style="margin-top: 16px;">
              <a href="{clean_url}" target="_blank" title="View this match on FanCode" style="display: inline-block; padding: 8px 16px; background-color: #2563eb; color: #ffffff !important; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 600; text-align: center;">
                {link_label_escaped}
              </a>
            </div>"""
        else:
            source_link_html = """
            <div style="margin-top: 14px;">
              <span style="display: inline-block; padding: 6px 12px; background-color: #f1f5f9; color: #94a3b8; border-radius: 4px; font-size: 12px; font-style: italic;">
                Source link unavailable
              </span>
            </div>"""

        # Unverified status warning callout box
        warning_banner_html = ""
        if meta["has_unverified"]:
            warning_banner_html = """
            <div style="margin-bottom: 12px; padding: 10px 14px; background-color: #fef3c7; border: 1px solid #fde68a; border-radius: 6px; font-size: 12px; color: #92400e; line-height: 1.4;">
              <strong>⚠️ Status Note:</strong> The latest scrape did not establish the current status. This may be a temporary data issue and does not confirm that the match has stopped.
            </div>"""

        return f"""
        <div class="entity-card" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
          <!-- Card Header & Badge -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 10px;">
            <tr>
              <td align="left" style="font-size: 12px; font-weight: 700; color: #64748b; letter-spacing: 0.5px; text-transform: uppercase;">
                {card_num_str} &bull; {category_escaped}
              </td>
              <td align="right">
                <span style="display: inline-block; padding: 3px 8px; font-size: 11px; font-weight: 700; border-radius: 4px; background-color: {meta['badge_bg']}; color: {meta['badge_color']}; letter-spacing: 0.5px; text-transform: uppercase;">
                  {badge_text_escaped}
                </span>
              </td>
            </tr>
          </table>

          <!-- Entity Title -->
          <h2 style="font-size: 17px; font-weight: 700; margin: 0 0 8px 0; color: #0f172a; line-height: 1.3;">
            {title_escaped}
          </h2>

          <!-- Context Row -->
          {context_html}

          <!-- Optional Warning Banner -->
          {warning_banner_html}

          <!-- What Changed Section -->
          <div style="margin-top: 12px;">
            <div style="font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">
              What changed?
            </div>
            {what_changed_table_html}
          </div>

          <!-- Why It Matters Section -->
          <div style="margin-top: 14px; padding: 10px 14px; background-color: #f8fafc; border-radius: 6px; border-left: 3px solid {meta['accent_color']};">
            <div style="font-size: 11px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">
              Why it matters
            </div>
            <div style="font-size: 13px; color: #334155; line-height: 1.4;">
              {why_it_matters_escaped}
            </div>
          </div>

          <!-- Action Button / Source Link -->
          {source_link_html}
        </div>"""
