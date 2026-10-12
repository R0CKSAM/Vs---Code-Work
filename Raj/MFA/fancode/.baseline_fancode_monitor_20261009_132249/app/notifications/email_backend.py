"""
email_backend.py – Email transport abstractions and development backends for FanCode (Phase 9).
"""

from __future__ import annotations

import logging
import os
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
        print("\n" + "=" * 70)
        print(f"EMAIL NOTIFICATION (CONSOLE BACKEND)")
        print(f"From:    {message.from_addr}")
        print(f"To:      {', '.join(message.to_addrs)}")
        if message.cc_addrs:
            print(f"Cc:      {', '.join(message.cc_addrs)}")
        print(f"Subject: {message.subject}")
        print("-" * 70)
        print(message.text_body)
        print("=" * 70 + "\n")

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
