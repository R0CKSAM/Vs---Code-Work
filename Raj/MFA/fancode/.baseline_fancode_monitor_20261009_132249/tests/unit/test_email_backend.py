"""
test_email_backend.py – Unit tests for Console, Test, and SMTP EmailBackends (Phase 9).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.notifications.email_backend import (
    ConsoleEmailBackend,
    TestEmailBackend,
)
from app.notifications.exceptions import ConfigurationError, DeliveryError
from app.notifications.models import EmailMessage
from app.notifications.smtp_backend import SmtpEmailBackend


@pytest.fixture
def sample_message():
    return EmailMessage(
        subject="Test Alert",
        html_body="<p>Test</p>",
        text_body="Test",
        from_addr="from@test.local",
        to_addrs=["to@test.local"],
        cc_addrs=["cc@test.local"],
    )


class TestEmailBackends:
    def test_console_backend_sends(self, sample_message, tmp_path):
        out_dir = str(tmp_path / "emails")
        backend = ConsoleEmailBackend(output_dir=out_dir)
        success = backend.send(sample_message)
        assert success is True

    def test_test_backend_records_messages(self, sample_message):
        backend = TestEmailBackend()
        assert len(backend.sent_messages) == 0

        backend.send(sample_message)
        assert len(backend.sent_messages) == 1
        assert backend.sent_messages[0].subject == "Test Alert"

        backend.clear()
        assert len(backend.sent_messages) == 0

    def test_test_backend_simulates_failure(self, sample_message):
        backend = TestEmailBackend(should_fail=True, fail_message="Simulated SMTP failure")
        with pytest.raises(DeliveryError, match="Simulated SMTP failure"):
            backend.send(sample_message)

    def test_smtp_backend_missing_config_raises(self, sample_message):
        backend = SmtpEmailBackend(host="")
        with pytest.raises(ConfigurationError, match="SMTP host is not configured"):
            backend.send(sample_message)

        empty_rcpt_msg = EmailMessage(
            subject="Test",
            html_body="<p>T</p>",
            text_body="T",
            from_addr="from@test.local",
            to_addrs=[],
        )
        valid_backend = SmtpEmailBackend(host="smtp.example.com")
        with pytest.raises(ConfigurationError, match="Cannot send email without recipients"):
            valid_backend.send(empty_rcpt_msg)

    @patch("smtplib.SMTP")
    def test_smtp_backend_send_success(self, mock_smtp_cls, sample_message):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.example.com",
            port=587,
            username="user",
            password="secret_password",
            use_tls=True,
        )
        success = backend.send(sample_message)
        assert success is True
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called()
        mock_server.login.assert_called_with("user", "secret_password")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    def test_smtp_ssl_backend_send_success(self, mock_smtp_ssl_cls, sample_message):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.gmail.com",
            port=465,
            username="rajxy91@gmail.com",
            password="app_password",
        )
        assert backend.use_ssl is True
        assert backend.use_tls is False

        success = backend.send(sample_message)
        assert success is True
        mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        mock_server.ehlo.assert_called()
        mock_server.login.assert_called_with("rajxy91@gmail.com", "app_password")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

