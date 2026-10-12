"""
send_test_notification.py – Sends a real test alert email with the redesigned notification layout.

Dispatches a test notification email using configured SMTP settings in .env
to verify mobile rendering, executive summary, numbered update cards, and dedicated source links.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging
from app.config.settings import settings
from app.change_detection.models import ChangeType, EntityType, Severity
from app.database.models import ChangeEvent
from app.notifications.grouping import EventGrouper
from app.notifications.models import EmailRecipientConfig
from app.notifications.renderer import NotificationRenderer
from app.notifications.smtp_backend import SmtpEmailBackend

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_notification")


def main() -> None:
    print("\n" + "=" * 70)
    print(" FanCode Monitor — Send Test Notification Email")
    print("=" * 70)

    # 1. Resolve recipients from settings (.env)
    to_raw = settings.ALERT_EMAIL_TO or settings.ALERT_RECIPIENTS or "admin@fancode-monitor.local"
    to_addrs = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
    from_addr = settings.ALERT_EMAIL_FROM or settings.SMTP_USER or "alerts@fancode-monitor.local"

    recipients = EmailRecipientConfig(
        from_addr=from_addr,
        to_addrs=to_addrs,
    )

    print(f"From: {recipients.from_addr}")
    print(f"To:   {', '.join(recipients.to_addrs)}")
    print(f"SMTP Host: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"SMTP SSL/TLS: SSL={settings.SMTP_USE_SSL}, TLS={settings.SMTP_USE_TLS}")
    print("-" * 70)

    # 2. Build representative sample events
    event1 = ChangeEvent(
        entity_type="match",
        entity_id=17,
        external_id="4249664",
        change_type="STATUS_CHANGED",
        field_name="status",
        old_value="LIVE",
        new_value="UNKNOWN",
        source_url="https://www.fancode.com/cricket/tour/sheffield-shield-2026-27-19896475/matches/queensland-vs-western-australia-4249664/live-match-info",
        severity="IMPORTANT",
        metadata_json={
            "title": "Queensland vs Western Australia",
            "sport": "Cricket",
            "tour": "Sheffield Shield 2026-27",
        },
    )

    event2 = ChangeEvent(
        entity_type="match",
        entity_id=1,
        external_id="4249721",
        change_type="UPDATED",
        field_name="start_time",
        old_value="09:00 UTC",
        new_value="10:30 UTC",
        source_url="https://www.fancode.com/cricket/tour/icc-mens-t20-world-cup-asia-qualifier-b-2026-19896480/matches/thailand-vs-qatar-4249721/live-match-info",
        severity="IMPORTANT",
        metadata_json={
            "title": "Thailand vs Qatar",
            "sport": "Cricket",
            "tour": "ICC Men's T20 World Cup Asia Qualifier B 2026",
        },
    )

    event3 = ChangeEvent(
        entity_type="video",
        entity_id=10,
        external_id="video-4249663",
        change_type="CREATED",
        field_name=None,
        old_value=None,
        new_value="Day 1 Highlights: Tasmania vs New South Wales",
        source_url="https://www.fancode.com/video/day-1-highlights-tasmania-vs-new-south-wales",
        severity="INFO",
        metadata_json={
            "title": "Day 1 Highlights: Tasmania vs New South Wales",
            "sport": "Cricket",
            "tour": "Sheffield Shield 2026-27",
        },
    )

    # 3. Create batch & render email
    batch = EventGrouper.create_batch([event1, event2, event3], scrape_run_id=999)
    assert batch is not None, "Failed to create notification batch"

    email_msg = NotificationRenderer.build_email_message(batch, recipients)
    print(f"\nRendered Subject: {email_msg.subject}")
    print(f"HTML Body Length: {len(email_msg.html_body)} bytes")
    print(f"Text Body Length: {len(email_msg.text_body)} bytes")

    # 4. Dispatch via SMTP backend
    print("\nConnecting to SMTP server and dispatching email...")
    backend = SmtpEmailBackend(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=settings.SMTP_USE_TLS,
        use_ssl=settings.SMTP_USE_SSL,
        timeout=settings.SMTP_TIMEOUT_SECONDS,
    )

    try:
        backend.send(email_msg)
        print("\n" + "=" * 70)
        print(f" SUCCESS: Test notification email sent to {', '.join(recipients.to_addrs)}")
        print(" Please check your inbox (and spam/promotions folder) on your phone.")
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"\n DELIVERY FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
