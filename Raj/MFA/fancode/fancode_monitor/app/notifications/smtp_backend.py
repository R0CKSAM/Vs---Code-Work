"""
smtp_backend.py – Production SMTP email delivery backend for FanCode (Phase 9).
"""

from __future__ import annotations

import logging
import smtplib
from email.utils import formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.notifications.email_backend import EmailBackend
from app.notifications.exceptions import ConfigurationError, DeliveryError
from app.notifications.models import EmailMessage

logger = logging.getLogger(__name__)


class SmtpEmailBackend(EmailBackend):
    """
    SMTP Email transport implementation.
    Handles TLS/SSL, authentication, timeouts, and MIME multipart assembly.
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        use_ssl: Optional[bool] = None,
        timeout: int = 15,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

        # If use_ssl is explicitly specified, use it.
        # Otherwise auto-detect: port 465 implies implicit SSL, whereas other ports default to use_ssl=False.
        if use_ssl is not None:
            self.use_ssl = bool(use_ssl)
        else:
            self.use_ssl = (self.port == 465)

        # If implicit SSL is used, STARTTLS should not be attempted.
        self.use_tls = use_tls if not self.use_ssl else False

    def _create_connection(self) -> smtplib.SMTP:
        """
        Establishes SMTP or SMTP_SSL connection, completes handshake, and authenticates if credentials are present.
        """
        if self.use_ssl:
            logger.debug("Connecting to SMTP server %s:%s via SMTP_SSL (implicit SSL)...", self.host, self.port)
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            server.ehlo()
        else:
            logger.debug("Connecting to SMTP server %s:%s (STARTTLS=%s)...", self.host, self.port, self.use_tls)
            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            server.ehlo()
            if self.use_tls:
                server.starttls()
                server.ehlo()

        if self.username and self.password:
            server.login(self.username, self.password)

        return server

    def verify_connection(self) -> bool:
        """
        Validates connection, TLS/SSL negotiation, and optional authentication without sending an email.
        Raises ConfigurationError on missing configuration.
        Raises DeliveryError on connection or authentication failure.
        """
        if not self.host:
            raise ConfigurationError("SMTP host is not configured.")

        try:
            server = self._create_connection()
            server.quit()
            logger.info("SMTP connection and authentication verified successfully.")
            return True
        except smtplib.SMTPAuthenticationError as e:
            # Credential identifiers are deliberately omitted from logs.
            logger.error("SMTP authentication failed: %s", e)
            raise DeliveryError(f"SMTP authentication failed: {e}") from e
        except smtplib.SMTPException as e:
            logger.error("SMTP transmission error: %s", e)
            raise DeliveryError(f"SMTP delivery error: {e}") from e
        except Exception as e:
            logger.error("Unexpected error during SMTP connection: %s", e)
            raise DeliveryError(f"Unexpected delivery error: {e}") from e

    def send(self, message: EmailMessage) -> bool:
        """
        Sends an EmailMessage over SMTP or SMTP_SSL.
        """
        if not self.host:
            raise ConfigurationError("SMTP host is not configured.")
        if not message.to_addrs:
            raise ConfigurationError("Cannot send email without recipients.")

        # Build MIME multipart message
        mime_msg = MIMEMultipart("alternative")
        mime_msg["Subject"] = message.subject
        mime_msg["From"] = message.from_addr
        mime_msg["To"] = ", ".join(message.to_addrs)
        mime_msg["Date"] = formatdate(localtime=False)
        mime_msg["Message-ID"] = make_msgid(domain=message.from_addr.rpartition("@")[2] or None)

        if message.cc_addrs:
            mime_msg["Cc"] = ", ".join(message.cc_addrs)

        for header_k, header_v in message.headers.items():
            mime_msg[header_k] = header_v

        # Attach text and html alternatives
        part_text = MIMEText(message.text_body, "plain", "utf-8")
        part_html = MIMEText(message.html_body, "html", "utf-8")
        mime_msg.attach(part_text)
        mime_msg.attach(part_html)

        all_recipients = list(dict.fromkeys(message.to_addrs + message.cc_addrs + message.bcc_addrs))

        server: Optional[smtplib.SMTP] = None
        try:
            server = self._create_connection()
            rejected = server.sendmail(message.from_addr, all_recipients, mime_msg.as_string())
            if isinstance(rejected, dict) and rejected:
                refused = ", ".join(sorted(rejected))
                raise DeliveryError(f"SMTP rejected recipient(s): {refused}")
            logger.info(
                "SMTP accepted alert email for %d configured recipient(s).",
                len(all_recipients),
            )
            return True
        except smtplib.SMTPAuthenticationError as e:
            # Credential identifiers are deliberately omitted from logs.
            logger.error("SMTP authentication failed: %s", e)
            raise DeliveryError(f"SMTP authentication failed: {e}") from e
        except smtplib.SMTPException as e:
            logger.error("SMTP transmission error: %s", e)
            raise DeliveryError(f"SMTP delivery error: {e}") from e
        except DeliveryError:
            raise
        except Exception as e:
            logger.error("Unexpected error during SMTP delivery: %s", e)
            raise DeliveryError(f"Unexpected delivery error: {e}") from e
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass
