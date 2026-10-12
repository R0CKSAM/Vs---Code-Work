"""
smtp_test.py – Operational CLI for testing SMTP connectivity and sending controlled test emails.

Usage:
  python -m app.notifications.smtp_test --check
  python -m app.notifications.smtp_test --send-test
  python -m app.notifications.smtp_test --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from app.config.settings import settings
from app.notifications.exceptions import ConfigurationError, DeliveryError
from app.notifications.models import EmailMessage
from app.notifications.smtp_backend import SmtpEmailBackend

logger = logging.getLogger("smtp_test")


def create_smtp_backend() -> SmtpEmailBackend:
    """Instantiates SmtpEmailBackend using central application settings."""
    port = getattr(settings, "SMTP_PORT", 587)
    use_ssl = getattr(settings, "SMTP_USE_SSL", False) or (port == 465)
    return SmtpEmailBackend(
        host=getattr(settings, "SMTP_HOST", ""),
        port=port,
        username=getattr(settings, "SMTP_USER", ""),
        password=getattr(settings, "SMTP_PASSWORD", ""),
        use_tls=getattr(settings, "SMTP_USE_TLS", True),
        use_ssl=use_ssl,
        timeout=getattr(settings, "SMTP_TIMEOUT_SECONDS", 15),
    )


def validate_smtp_config(require_recipient: bool = False) -> List[str]:
    """
    Validates essential SMTP configuration settings.
    Returns a list of error description strings (empty if valid).
    Never prints or reveals credentials/passwords.
    """
    errors: List[str] = []

    host = getattr(settings, "SMTP_HOST", "")
    if not host or not str(host).strip():
        errors.append("SMTP_HOST is not configured in environment or .env.")

    port = getattr(settings, "SMTP_PORT", 587)
    try:
        port_num = int(port)
        if port_num <= 0 or port_num > 65535:
            errors.append(f"SMTP_PORT must be between 1 and 65535 (got: {port}).")
    except (ValueError, TypeError):
        errors.append(f"SMTP_PORT must be a valid integer (got: {port}).")

    user = getattr(settings, "SMTP_USER", "")
    password = getattr(settings, "SMTP_PASSWORD", "")
    if user and not password:
        errors.append("SMTP_USER is configured, but SMTP_PASSWORD is not set in .env (a 16-character Google App Password is required).")

    if require_recipient:
        to_addr = getattr(settings, "ALERT_EMAIL_TO", "") or getattr(settings, "ALERT_RECIPIENTS", "")
        if not to_addr or not str(to_addr).strip():
            errors.append("ALERT_EMAIL_TO or ALERT_RECIPIENTS is not configured.")

        from_addr = getattr(settings, "ALERT_EMAIL_FROM", "")
        if not from_addr or not str(from_addr).strip():
            errors.append("ALERT_EMAIL_FROM is not configured.")

    return errors


def build_test_email_message(to_address: Optional[str] = None) -> EmailMessage:
    """Constructs the unmistakable, controlled test email message."""
    smtp_user = getattr(settings, "SMTP_USER", "")
    configured_from = getattr(settings, "ALERT_EMAIL_FROM", "")
    # If ALERT_EMAIL_FROM is empty or default placeholder but SMTP_USER is set, use SMTP_USER
    if configured_from and configured_from != "alerts@fancode-monitor.local":
        from_addr = configured_from
    elif smtp_user and "@" in smtp_user:
        from_addr = smtp_user
    else:
        from_addr = configured_from or "alerts@fancode-monitor.local"

    target_to = to_address or getattr(settings, "ALERT_EMAIL_TO", "") or getattr(settings, "ALERT_RECIPIENTS", "admin@fancode-monitor.local")

    to_addrs = [addr.strip() for addr in target_to.split(",") if addr.strip()]

    subject = "FanCode Monitor — SMTP Test"
    text_body = (
        "This is a controlled SMTP test from the FanCode Monitoring System.\n\n"
        "SMTP connectivity:\n"
        "PASS\n\n"
        "Notification delivery path:\n"
        "SMTP\n\n"
        "This message confirms that the configured SMTP connection can deliver email."
    )
    html_body = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><meta charset='utf-8'></head>\n"
        "<body style='font-family: Arial, sans-serif; line-height: 1.6; color: #222; max-width: 600px; margin: 0 auto; padding: 20px;'>\n"
        "  <div style='background-color: #0f172a; padding: 16px; border-radius: 8px 8px 0 0; color: #ffffff;'>\n"
        "    <h2 style='margin: 0; font-size: 18px;'>FanCode Monitor — SMTP Test</h2>\n"
        "  </div>\n"
        "  <div style='border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;'>\n"
        "    <p>This is a controlled SMTP test from the FanCode Monitoring System.</p>\n"
        "    <table style='width: 100%; border-collapse: collapse; margin: 16px 0;'>\n"
        "      <tr>\n"
        "        <td style='padding: 8px; border: 1px solid #e2e8f0; font-weight: bold; background: #f8fafc;'>SMTP connectivity:</td>\n"
        "        <td style='padding: 8px; border: 1px solid #e2e8f0; color: #16a34a; font-weight: bold;'>PASS</td>\n"
        "      </tr>\n"
        "      <tr>\n"
        "        <td style='padding: 8px; border: 1px solid #e2e8f0; font-weight: bold; background: #f8fafc;'>Notification delivery path:</td>\n"
        "        <td style='padding: 8px; border: 1px solid #e2e8f0;'>SMTP</td>\n"
        "      </tr>\n"
        "    </table>\n"
        "    <p style='color: #475569; font-size: 14px;'>This message confirms that the configured SMTP connection can deliver email.</p>\n"
        "  </div>\n"
        "</body>\n"
        "</html>"
    )

    return EmailMessage(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_addr=from_addr,
        to_addrs=to_addrs,
    )


def run_smtp_check() -> int:
    """
    Performs connection and authentication verification without sending email.
    Returns 0 on success, 1 on error.
    """
    errors = validate_smtp_config(require_recipient=False)
    if errors:
        print("\n[ERROR] SMTP Configuration Invalid:")
        for err in errors:
            print(f"  - {err}")
        return 1

    host = getattr(settings, "SMTP_HOST", "")
    port = getattr(settings, "SMTP_PORT", 587)
    user = getattr(settings, "SMTP_USER", "")
    backend = create_smtp_backend()
    sec_mode = "SMTP_SSL (Implicit SSL)" if backend.use_ssl else f"STARTTLS={backend.use_tls}"

    print(f"\nChecking SMTP connection to {host}:{port} (Security={sec_mode}, Auth={'Configured' if user else 'None'})...")

    try:
        backend.verify_connection()
        print("SMTP connection: PASS")
        if user:
            print("Authentication: PASS")
        print("\n[SUCCESS] SMTP server is reachable and credentials are valid.\n")
        return 0
    except ConfigurationError as e:
        print(f"\n[ERROR] Configuration error: {e}")
        return 1
    except DeliveryError as e:
        print(f"\n[ERROR] Delivery/Connection error: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return 1


def run_send_test(recipient: Optional[str] = None) -> int:
    """
    Sends one controlled test email to verified recipient.
    Returns 0 on success, 1 on error.
    """
    errors = validate_smtp_config(require_recipient=True)
    if errors:
        print("\n[ERROR] SMTP Configuration Invalid:")
        for err in errors:
            print(f"  - {err}")
        return 1

    backend = create_smtp_backend()
    msg = build_test_email_message(to_address=recipient)

    print(f"\nAttempting to send controlled test email to: {', '.join(msg.to_addrs)}")
    print(f"From: {msg.from_addr}")
    print(f"Subject: {msg.subject}\n")

    try:
        backend.send(msg)
        print("SMTP connection: PASS")
        if getattr(settings, "SMTP_USER", ""):
            print("Authentication: PASS")
        print("Test email: SENT")
        print(f"\n[SUCCESS] Test email delivered successfully to {', '.join(msg.to_addrs)}.\n")
        return 0
    except ConfigurationError as e:
        print(f"\n[ERROR] Configuration error: {e}")
        return 1
    except DeliveryError as e:
        print(f"\n[ERROR] Delivery error: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.notifications.smtp_test",
        description="FanCode Monitor – SMTP Connectivity and Verification CLI",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="Verify SMTP connectivity, TLS negotiation, and credentials without sending an email",
    )
    group.add_argument(
        "--send-test",
        action="store_true",
        help="Send a single controlled test email to verify end-to-end inbox delivery",
    )
    parser.add_argument(
        "--to",
        type=str,
        default=None,
        help="Optional recipient override for test email (defaults to ALERT_EMAIL_TO)",
    )

    args = parser.parse_args(argv)

    if args.check:
        return run_smtp_check()
    elif args.send_test:
        return run_send_test(recipient=args.to)

    return 0


if __name__ == "__main__":
    sys.exit(main())
