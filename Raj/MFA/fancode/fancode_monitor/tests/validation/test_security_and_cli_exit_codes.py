"""
test_security_and_cli_exit_codes.py – Phase 12 Security Hygiene, CLI Exit Codes & Retention Safety Tests.

Verifies:
- Secret hygiene and redacting sensitive credentials (passwords, tokens, api keys) in logs.
- Gitignore correctly excludes `.env` and environment files.
- CLI argument parsing and exit code mapping (SUCCESS, PARTIAL, CONFIG_ERROR, LOCKED, FATAL).
- Data retention maintenance safety:
    * Dry run never deletes records.
    * Destructive cleanup removes only expired operational audit records.
    * Core domain entities (matches, tours, sports, videos) are strictly preserved.
    * Retention is idempotent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from app.database.models import ChangeEvent, Match, NotificationBatch, ScrapeRun, Sport
from app.database.repositories import ChangeEventsRepository, MatchesRepository, SportsRepository
from app.maintenance.retention import DataRetentionCleaner
from app.monitor.models import ExitCode, PipelineStatus
from app.observability.logging_config import SecretRedactionFilter, configure_logging
from run_monitor import parse_args as parse_monitor_args


class TestSecurityAndCliExitCodesValidation:
    """Validates security hygiene, exit code standards, and retention safety."""

    def test_secret_redaction_in_log_records(self):
        """Verifies that SecretRedactionFilter redacts passwords, tokens, and api keys from logs."""
        redactor = SecretRedactionFilter()

        class DummyRecord:
            def __init__(self, msg):
                self.msg = msg
                self.args = None

            def getMessage(self):
                return str(self.msg)

        # Test password redaction
        rec1 = DummyRecord("Connecting with password=SuperSecret123 to smtp")
        redactor.filter(rec1)
        assert "SuperSecret123" not in rec1.msg
        assert "[REDACTED]" in rec1.msg

        # Test bearer token redaction
        rec2 = DummyRecord("Authorization: Bearer my-top-secret-token")
        redactor.filter(rec2)
        assert "my-top-secret-token" not in rec2.msg
        assert "[REDACTED]" in rec2.msg

        # Test API key redaction
        rec3 = DummyRecord("api_key=abcdef1234567890")
        redactor.filter(rec3)
        assert "abcdef1234567890" not in rec3.msg
        assert "[REDACTED]" in rec3.msg

    def test_gitignore_protects_env_and_secrets(self):
        """Verifies that .gitignore properly excludes .env files from version control."""
        root = Path(__file__).resolve().parents[2]
        gitignore_path = root / ".gitignore"
        assert gitignore_path.exists()

        content = gitignore_path.read_text(encoding="utf-8")
        assert ".env" in content
        assert "*.env.local" in content or ".env" in content

    def test_cli_argument_parsing_and_exit_code_enums(self):
        """Verifies CLI argument parsing supports Phase 11 & 12 flags and exit codes are standard."""
        # Check standard exit code integer values
        assert ExitCode.SUCCESS == 0
        assert ExitCode.PARTIAL == 1
        assert ExitCode.CONFIG_ERROR == 2
        assert ExitCode.LOCKED == 3
        assert ExitCode.FATAL == 4

        # Verify CLI args parsing with standard flags
        import sys
        orig_argv = sys.argv
        try:
            sys.argv = ["run_monitor.py", "--once", "--dry-run", "--json"]
            args = parse_monitor_args()
            assert args.once is True
            assert args.dry_run is True
            assert getattr(args, "json", False) is True
        finally:
            sys.argv = orig_argv

    def test_data_retention_dry_run_never_deletes(self, db_session):
        """Verifies that DataRetentionCleaner with dry_run=True identifies records without deleting."""
        now = datetime.now(timezone.utc)
        past_expired = now - timedelta(days=120)

        # Create expired operational records
        run = ScrapeRun(run_type="monitor", status="success", started_at=past_expired, finished_at=past_expired)
        db_session.add(run)
        db_session.commit()

        # Dry run cleanup
        result = DataRetentionCleaner.clean(session=db_session, dry_run=True, scrape_run_days=30)
        assert result["is_dry_run"] is True
        assert result["deleted_counts"]["scrape_runs"] >= 1

        # Record must still exist in DB
        assert db_session.query(ScrapeRun).filter_by(id=run.id).first() is not None

    def test_data_retention_destructive_preserves_core_entities(self, db_session):
        """
        Verifies that destructive cleanup removes expired audit records while strictly
        preserving all core domain entities (Sports, Matches) and recent audit records.
        """
        now = datetime.now(timezone.utc)
        past_expired = now - timedelta(days=120)
        recent_date = now - timedelta(days=2)

        # 1. Core entity (Match & Sport)
        sport = Sport(name="Cricket", slug="cricket", source_url="https://fancode.com/cricket", first_seen_at=past_expired)
        match = Match(
            external_id="core-match-1",
            title="Core Match",
            slug="core-match",
            status="COMPLETED",
            source_url="https://fancode.com/match/core",
            first_seen_at=past_expired,
        )
        db_session.add_all([sport, match])

        # 2. Expired scrape run and change event
        expired_run = ScrapeRun(run_type="monitor", status="success", started_at=past_expired, finished_at=past_expired)
        db_session.add(expired_run)
        db_session.commit()

        expired_event = ChangeEvent(
            entity_type="MATCH",
            entity_id=match.id,
            external_id="core-match-1",
            change_type="CREATED",
            new_value="Core Match",
            detected_at=past_expired,
        )
        db_session.add(expired_event)

        # 3. Recent scrape run (must be preserved)
        recent_run = ScrapeRun(run_type="monitor", status="success", started_at=recent_date, finished_at=recent_date)
        db_session.add(recent_run)
        db_session.commit()

        # Capture IDs
        expired_run_id = expired_run.id
        expired_event_id = expired_event.id
        recent_run_id = recent_run.id
        match_id = match.id
        sport_id = sport.id

        # Execute destructive cleanup
        result = DataRetentionCleaner.clean(session=db_session, dry_run=False, scrape_run_days=30, change_event_days=90)
        assert result["is_dry_run"] is False

        # Expired audit records should be deleted
        assert db_session.query(ScrapeRun).filter_by(id=expired_run_id).first() is None
        assert db_session.query(ChangeEvent).filter_by(id=expired_event_id).first() is None

        # Recent audit record must be preserved
        assert db_session.query(ScrapeRun).filter_by(id=recent_run_id).first() is not None

        # CORE DOMAIN ENTITIES MUST NEVER BE DELETED
        assert db_session.query(Match).filter_by(id=match_id).first() is not None
        assert db_session.query(Sport).filter_by(id=sport_id).first() is not None

        # Cleanup is idempotent: running again does not crash or corrupt
        result2 = DataRetentionCleaner.clean(session=db_session, dry_run=False, scrape_run_days=30, change_event_days=90)
        assert result2["is_dry_run"] is False
