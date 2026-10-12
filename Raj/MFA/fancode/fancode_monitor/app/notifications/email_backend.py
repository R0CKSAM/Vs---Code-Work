"""
email_backend.py – Email transport abstractions and development backends for FanCode (Phase 9).
"""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import List, Optional

from app.notifications.exceptions import DeliveryError
from app.notifications.models import EmailMessage

logger = logging.getLogger(__name__)


class EmailBackend(ABC):
    """Abstract base class for all notification email backends."""

    @abstractmethod
    def send(self, message: EmailMessage) -> bool:
        """
        Sends an EmailMessage.
        Returns True on success, or raises DeliveryError on failure.
        """
        pass


class ConsoleEmailBackend(EmailBackend):
    """
    Development email backend.
    Logs and prints email digests without sending network packets.
    """

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir

    def send(self, message: EmailMessage) -> bool:
        logger.info(
            "ConsoleEmailBackend: [To: %s] Subject: %s",
            ", ".join(message.to_addrs),
            message.subject,
        )
        lines = [
            "",
            "=" * 70,
            "EMAIL NOTIFICATION (CONSOLE BACKEND)",
            f"From:    {message.from_addr}",
            f"To:      {', '.join(message.to_addrs)}",
        ]
        if message.cc_addrs:
            lines.append(f"Cc:      {', '.join(message.cc_addrs)}")
        lines.extend([
            f"Subject: {message.subject}",
            "-" * 70,
            message.text_body,
            "=" * 70,
            "",
        ])
        payload = "\n".join(lines) + "\n"
        try:
            sys.stdout.write(payload)
            sys.stdout.flush()
        except UnicodeEncodeError:
            # Windows may inherit a legacy cp1252 console. Write UTF-8 bytes
            # when possible; otherwise preserve content with escaped codepoints.
            buffer = getattr(sys.stdout, "buffer", None)
            if buffer is not None:
                buffer.write(payload.encode("utf-8"))
                buffer.flush()
            else:
                encoding = getattr(sys.stdout, "encoding", None) or "ascii"
                sys.stdout.write(payload.encode(encoding, errors="backslashreplace").decode(encoding))

        # Optionally save rendered HTML/text to disk
        if self.output_dir:
            try:
                os.makedirs(self.output_dir, exist_ok=True)
                filename_base = f"digest_{message.created_at.strftime('%Y%m%d_%H%M%S')}"
                html_path = os.path.join(self.output_dir, f"{filename_base}.html")
                text_path = os.path.join(self.output_dir, f"{filename_base}.txt")

                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(message.html_body)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(message.text_body)
                logger.debug("Saved notification digest to %s and %s", html_path, text_path)
            except Exception as e:
                logger.warning("Failed to save email file output: %s", e)

        return True


class TestEmailBackend(EmailBackend):
    """
    In-memory email backend for unit and integration testing.
    Records all dispatched messages and allows simulating failures.
    """
    __test__ = False

    def __init__(self, should_fail: bool = False, fail_message: str = "Simulated delivery failure") -> None:
        self.sent_messages: List[EmailMessage] = []
        self.should_fail = should_fail
        self.fail_message = fail_message

    def send(self, message: EmailMessage) -> bool:
        if self.should_fail:
            raise DeliveryError(self.fail_message)

        self.sent_messages.append(message)
        logger.debug("TestEmailBackend recorded message: %s", message.subject)
        return True

    def clear(self) -> None:
        self.sent_messages.clear()
