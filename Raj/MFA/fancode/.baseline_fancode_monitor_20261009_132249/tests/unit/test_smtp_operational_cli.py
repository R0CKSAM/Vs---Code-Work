"""
test_smtp_operational_cli.py – Unit and operational tests for SMTP connectivity CLI (smtp_test.py) and SmtpEmailBackend.

Verifies:
- Configuration validation (missing host, invalid port, missing recipients).
- Secret redaction (passwords and credentials never printed in stdout/stderr).
- CLI exit codes (0 for success, non-zero for failures).
- Mocked SMTP connection verification.
- Mocked controlled test email dispatch.
- End-to-end integration: change event -> notification service -> SMTP transport (mocked).
"""

from __future__ import annotations

import io
import smtplib
from email import policy
from email.parser import Parser
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import Settings
from app.database.connection import utc_now
from app.database.models import ChangeEvent, Match
from app.database.repositories import ChangeEventsRepository, MatchesRepository
from app.notifications.email_backend import EmailBackend
from app.notifications.exceptions import ConfigurationError, DeliveryError
from app.notifications.models import EmailMessage, EmailRecipientConfig
from app.notifications.service import NotificationService
from app.notifications.smtp_backend import SmtpEmailBackend
from app.notifications.smtp_test import (
    build_test_email_message,
    main,
    run_send_test,
    run_smtp_check,
    validate_smtp_config,
)


class TestSmtpConfigurationValidation:
    """Tests configuration checking and validation without network interaction."""

    def test_missing_smtp_host_detected(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "")
        errors = validate_smtp_config(require_recipient=False)
        assert len(errors) >= 1
        assert any("SMTP_HOST" in err for err in errors)

    def test_invalid_smtp_port_detected(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", -1)
        errors = validate_smtp_config(require_recipient=False)
        assert len(errors) >= 1
        assert any("SMTP_PORT" in err for err in errors)

    def test_missing_recipient_detected_when_required(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 587)
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_RECIPIENTS", "")

        errors = validate_smtp_config(require_recipient=True)
        assert len(errors) >= 1
        assert any("ALERT_EMAIL_TO" in err for err in errors)

    def test_missing_password_when_user_configured_detected(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 465)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "")
        errors = validate_smtp_config(require_recipient=False)
        assert len(errors) >= 1
        assert any("SMTP_PASSWORD" in err for err in errors)

    def test_valid_smtp_config_returns_zero_errors(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 587)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "valid_app_pass")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "admin@fancode.local")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_FROM", "alerts@fancode.local")

        errors = validate_smtp_config(require_recipient=True)
        assert errors == []

    def test_build_test_email_message_uses_configured_sender_and_recipient(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_FROM", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "rajxy101@gmail.com")

        msg = build_test_email_message()
        assert msg.from_addr == "rajxy91@gmail.com"
        assert msg.to_addrs == ["rajxy101@gmail.com"]
        assert msg.subject == "FanCode Monitor — SMTP Test"

    def test_build_test_email_message_falls_back_to_smtp_user_when_default_from(self, monkeypatch):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_FROM", "alerts@fancode-monitor.local")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "rajxy101@gmail.com")

        msg = build_test_email_message()
        assert msg.from_addr == "rajxy91@gmail.com"
        assert msg.to_addrs == ["rajxy101@gmail.com"]


class TestSmtpBackendVerificationMethod:
    """Tests verify_connection() on SmtpEmailBackend with mocked SMTP and SMTP_SSL transports."""

    @patch("smtplib.SMTP")
    def test_verify_connection_port_587_uses_starttls(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="test_password",
            use_tls=True,
        )
        assert backend.use_ssl is False
        assert backend.use_tls is True
        assert backend.verify_connection() is True

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=15)
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_with("user@example.com", "test_password")
        mock_server.quit.assert_called()

    @patch("smtplib.SMTP_SSL")
    @patch("smtplib.SMTP")
    def test_verify_connection_port_465_uses_smtp_ssl_without_starttls(self, mock_smtp_cls, mock_smtp_ssl_cls):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.gmail.com",
            port=465,
            username="rajxy101@gmail.com",
            password="test_app_password",
        )
        assert backend.use_ssl is True
        assert backend.use_tls is False
        assert backend.verify_connection() is True

        # Must use smtplib.SMTP_SSL, not smtplib.SMTP
        mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        mock_smtp_cls.assert_not_called()
        mock_server.ehlo.assert_called()
        # Must NEVER call starttls on port 465
        assert not hasattr(mock_server, "starttls") or not mock_server.starttls.called
        mock_server.login.assert_called_with("rajxy101@gmail.com", "test_app_password")
        mock_server.quit.assert_called()

    @patch("smtplib.SMTP_SSL")
    def test_explicit_use_ssl_true_uses_smtp_ssl(self, mock_smtp_ssl_cls):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.custom.local",
            port=465,
            use_ssl=True,
        )
        assert backend.use_ssl is True
        assert backend.verify_connection() is True
        mock_smtp_ssl_cls.assert_called_once_with("smtp.custom.local", 465, timeout=15)

    @patch("smtplib.SMTP")
    def test_verify_connection_auth_failure_raises_delivery_error(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp_cls.return_value = mock_server

        backend = SmtpEmailBackend(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="wrong_password",
            use_tls=True,
        )
        with pytest.raises(DeliveryError, match="SMTP authentication failed"):
            backend.verify_connection()

    @patch("smtplib.SMTP")
    def test_verify_connection_network_error_raises_delivery_error(self, mock_smtp_cls):
        mock_smtp_cls.side_effect = smtplib.SMTPConnectError(421, b"Connection refused")

        backend = SmtpEmailBackend(host="smtp.unreachable.local", port=587)
        with pytest.raises(DeliveryError, match="SMTP delivery error"):
            backend.verify_connection()


class TestSmtpOperationalCli:
    """Tests the CLI entrypoint commands and exit codes."""

    def test_check_fails_with_missing_host(self, monkeypatch, capsys):
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "")
        code = main(["--check"])
        captured = capsys.readouterr()
        assert code == 1
        assert "SMTP_HOST is not configured" in captured.out

    @patch("smtplib.SMTP")
    def test_check_succeeds_with_mocked_server(self, mock_smtp_cls, monkeypatch, capsys):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 587)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "user@example.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "secret123")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USE_SSL", False)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USE_TLS", True)

        code = main(["--check"])
        captured = capsys.readouterr()
        assert code == 0
        assert "SMTP connection: PASS" in captured.out
        assert "Authentication: PASS" in captured.out
        # Strict secret protection check: password must NEVER be in stdout
        assert "secret123" not in captured.out

    @patch("smtplib.SMTP_SSL")
    def test_check_port_465_uses_smtp_ssl(self, mock_smtp_ssl_cls, monkeypatch, capsys):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 465)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "secret123")

        code = main(["--check"])
        captured = capsys.readouterr()
        assert code == 0
        assert "Security=SMTP_SSL (Implicit SSL)" in captured.out
        assert "SMTP connection: PASS" in captured.out
        assert "Authentication: PASS" in captured.out
        mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        # Strict secret protection check: password must NEVER be in stdout
        assert "secret123" not in captured.out

    @patch("smtplib.SMTP")
    def test_send_test_succeeds_with_mocked_server(self, mock_smtp_cls, monkeypatch, capsys):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 587)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USE_SSL", False)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USE_TLS", True)
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "recipient@example.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_FROM", "alerts@example.com")

        code = main(["--send-test"])
        captured = capsys.readouterr()
        assert code == 0
        assert "Test email: SENT" in captured.out
        mock_server.sendmail.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    def test_send_test_port_465_uses_smtp_ssl(self, mock_smtp_ssl_cls, monkeypatch, capsys):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PORT", 465)
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_USER", "rajxy91@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.SMTP_PASSWORD", "app_pass")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_TO", "rajxy101@gmail.com")
        monkeypatch.setattr("app.notifications.smtp_test.settings.ALERT_EMAIL_FROM", "rajxy91@gmail.com")

        code = main(["--send-test"])
        captured = capsys.readouterr()
        assert code == 0
        assert "Test email: SENT" in captured.out
        mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        mock_server.sendmail.assert_called_once()
        from_arg, to_arg, raw_msg = mock_server.sendmail.call_args[0]
        assert from_arg == "rajxy91@gmail.com"
        assert to_arg == ["rajxy101@gmail.com"]
        # Verify app_password is NOT leaked to console
        assert "app_pass" not in captured.out


class TestEndToEndNotificationToSmtp:
    """Verifies change event generation through NotificationService directly into SmtpEmailBackend."""

    @patch("smtplib.SMTP_SSL")
    def test_change_event_to_smtp_ssl_delivery_port_465(self, mock_smtp_ssl_cls, db_session):
        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server

        # 1. Create a change event in the DB
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=502,
            external_id="match-e2e-502",
            change_type="CREATED",
            field_name=None,
            new_value="India vs Australia Final",
            severity="CRITICAL",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        # 2. Configure SmtpEmailBackend on port 465
        smtp_backend = SmtpEmailBackend(
            host="smtp.gmail.com",
            port=465,
            username="rajxy91@gmail.com",
            password="secret_pass",
        )
        assert smtp_backend.use_ssl is True
        recipients = EmailRecipientConfig(
            from_addr="rajxy91@gmail.com",
            to_addrs=["rajxy101@gmail.com"],
        )

        service = NotificationService(session=db_session, backend=smtp_backend, recipients=recipients)

        # 3. Run notification pipeline
        result = service.run()

        assert result.emails_sent == 1
        assert result.deliveries_failed == 0
        mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=15)
        mock_server.sendmail.assert_called_once()
        from_arg, to_arg, raw_msg = mock_server.sendmail.call_args[0]
        assert from_arg == "rajxy91@gmail.com"
        assert to_arg == ["rajxy101@gmail.com"]

    @patch("smtplib.SMTP")
    def test_change_event_to_smtp_delivery(self, mock_smtp_cls, db_session):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        # 1. Create a change event in the DB
        event = ChangeEvent(
            entity_type="MATCH",
            entity_id=501,
            external_id="match-e2e-501",
            change_type="CREATED",
            field_name=None,
            new_value="India vs Pakistan",
            severity="CRITICAL",
            detected_at=utc_now(),
        )
        db_session.add(event)
        db_session.commit()

        # 2. Configure SmtpEmailBackend and NotificationService
        smtp_backend = SmtpEmailBackend(
            host="smtp.example.com",
            port=587,
            username="bot@fancode.local",
            password="pass",
            use_tls=True,
        )
        recipients = EmailRecipientConfig(
            from_addr="alerts@fancode.local",
            to_addrs=["fan@fancode.local"],
        )

        service = NotificationService(session=db_session, backend=smtp_backend, recipients=recipients)

        # 3. Run notification pipeline
        result = service.run()

        assert result.emails_sent == 1
        assert result.deliveries_failed == 0
        mock_server.sendmail.assert_called_once()

        # Verify call args
        from_arg = mock_server.sendmail.call_args[0][0]
        to_arg = mock_server.sendmail.call_args[0][1]
        raw_msg = mock_server.sendmail.call_args[0][2]

        assert from_arg == "alerts@fancode.local"
        assert to_arg == ["fan@fancode.local"]
        parsed = Parser(policy=policy.default).parsestr(raw_msg)
        assert parsed["Subject"] == "FanCode Monitor — NEW Match: India vs Pakistan"
        assert parsed.get_body(preferencelist=("plain",)).get_content_type() == "text/plain"
        assert parsed.get_body(preferencelist=("html",)).get_content_type() == "text/html"
        assert "India vs Pakistan" in parsed.get_body(preferencelist=("plain",)).get_content()
        assert "India vs Pakistan" in parsed.get_body(preferencelist=("html",)).get_content()

        # 4. Idempotency: second run dispatches 0 emails
        result_idemp = service.run()
        assert result_idemp.emails_sent == 0
        assert mock_server.sendmail.call_count == 1
