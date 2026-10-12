"""Transactional email delivery for authentication workflows."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("email-service")


def send_password_reset_email(recipient: str, reset_url: str) -> bool:
    """Send a one-time password reset link without exposing any stored password."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD or not settings.SMTP_FROM_EMAIL:
        logger.error(
            "Password reset email was requested for %s, but SMTP credentials are not configured.",
            recipient,
        )
        return False

    message = EmailMessage()
    message["Subject"] = "Reset your Media Monitor password"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your Media Monitor account.\n\n"
        f"Open this link within {settings.PASSWORD_RESET_MINUTES} minutes:\n{reset_url}\n\n"
        "If you did not request this change, ignore this email. Your password remains unchanged."
    )
    message.add_alternative(
        f"""
        <html><body style="font-family:Arial,sans-serif;color:#0f172a;line-height:1.5">
          <h2>Reset your Media Monitor password</h2>
          <p>A password reset was requested for your account.</p>
          <p><a href="{reset_url}" style="display:inline-block;padding:10px 16px;background:#0284c7;color:#fff;text-decoration:none;border-radius:5px">Reset password</a></p>
          <p>This link expires in {settings.PASSWORD_RESET_MINUTES} minutes and can be used once.</p>
          <p>If you did not request this, ignore this email.</p>
        </body></html>
        """,
        subtype="html",
    )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls(context=context)
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        logger.info("Password reset email sent to %s", recipient)
        return True
    except Exception as exc:
        logger.error("Unable to send password reset email to %s: %s", recipient, exc)
        return False
