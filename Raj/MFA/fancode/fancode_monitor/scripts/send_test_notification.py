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
from app.database.connection import get_session, init_db
from app.notifications.repository import NotificationRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_notification")


def _mask_email(address: str) -> str:
    """Mask an address before putting credential identifiers in console logs."""
    local, separator, domain = address.partition("@")
    if not separator:
        return "<configured>"
    return f"{local[:1]}***@{domain}"


def main() -> None:
    # Windows consoles and redirected PowerShell streams may default to cp1252.
    # Force UTF-8 before rendering subjects that intentionally contain emoji.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="backslashreplace")
    print("\n" + "=" * 70)
    print(" FanCode Monitor — Send Test Notification Email")
    print("=" * 70)

    # 1. Resolve recipients from settings (.env)
    to_raw = settings.ALERT_EMAIL_TO or settings.ALERT_RECIPIENTS
    to_addrs = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
    from_addr = settings.ALERT_EMAIL_FROM or settings.SMTP_USER
    if not settings.SMTP_HOST or not to_addrs or not from_addr:
        raise SystemExit("SMTP sender and .env recipient configuration are required")
    if any(address.endswith("@fancode-monitor.local") for address in [from_addr, *to_addrs]):
        raise SystemExit("Refusing real delivery to placeholder addresses; configure .env")

    recipients = EmailRecipientConfig(
        from_addr=from_addr,
        to_addrs=to_addrs,
    )

    print(f"From: {_mask_email(recipients.from_addr)}")
    print(f"To:   {', '.join(_mask_email(a) for a in recipients.to_addrs)}")
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
        # The standalone operational test participates in the same audit trail
        # as monitor deliveries, without inventing change-event foreign keys.
        init_db()
        with get_session() as session:
            repo = NotificationRepository(session)
            db_batch = repo.create_batch(
                batch_key=batch.batch_key,
                subject=email_msg.subject,
                event_count=batch.event_count,
                recipient_count=len(recipients.all_recipients),
                status="PENDING",
                metadata_json={"source": "send_test_notification"},
            )
            for recipient in recipients.all_recipients:
                repo.record_delivery(db_batch.id, recipient, status="SENT", provider="smtp")
            repo.mark_batch_sent(db_batch.id)
        print("\n" + "=" * 70)
        print(f" SUCCESS: SMTP accepted the test email for {', '.join(_mask_email(a) for a in recipients.to_addrs)}")
        print(" Please check your inbox (and spam/promotions folder) on your phone.")
        print("=" * 70 + "\n")
    except Exception as e:
        print(f"\n DELIVERY FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
