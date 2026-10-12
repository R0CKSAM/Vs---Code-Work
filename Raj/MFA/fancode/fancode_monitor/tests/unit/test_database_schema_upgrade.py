"""
test_database_schema_upgrade.py – Unit tests for idempotent database schema upgrade and migration.

Verifies:
- Fresh database creation creates all tables and columns.
- Pre-existing database missing `change_events.severity` is upgraded safely without data loss.
- Existing rows are preserved intact.
- Re-running init_db is completely idempotent.
- Notification and change detection queries work smoothly after upgrade.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.change_detection.detector import ChangeDetector
from app.database.connection import Base, _upgrade_schema, init_db, utc_now
from app.database.models import ChangeEvent, Match, NotificationBatch, ScrapeRun
from app.notifications.repository import NotificationRepository


class TestDatabaseSchemaUpgrade:
    def test_fresh_database_creation(self, tmp_path):
        db_path = tmp_path / "fresh.db"
        engine = create_engine(f"sqlite:///{db_path}")

        init_db(engine)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        assert "sports" in tables
        assert "tours" in tables
        assert "matches" in tables
        assert "videos" in tables
        assert "pages" in tables
        assert "change_events" in tables
        assert "scrape_runs" in tables
        assert "notification_batches" in tables
        assert "notification_deliveries" in tables
        assert "notification_event_links" in tables

        ce_columns = {col["name"] for col in inspector.get_columns("change_events")}
        assert "severity" in ce_columns
        assert "external_id" in ce_columns
        assert "scrape_run_id" in ce_columns
        assert "metadata_json" in ce_columns
        assert "detected_at" in ce_columns

        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        match_indexes = {idx["name"]: idx for idx in inspector.get_indexes("matches")}
        assert "uq_matches_external_id_not_null" in match_indexes or any(
            idx.get("unique") and idx.get("column_names") == ["external_id"]
            for idx in match_indexes.values()
        )

        link_indexes = {idx["name"]: idx for idx in inspector.get_indexes("notification_event_links")}
        assert "uq_notification_event_link" in link_indexes or any(
            idx.get("unique") and idx.get("column_names") == ["batch_id", "change_event_id"]
            for idx in link_indexes.values()
        )

    def test_upgrade_existing_db_missing_severity(self, tmp_path):
        db_path = tmp_path / "legacy.db"

        # 1. Create a legacy SQLite table without the 'severity' column
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE change_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER NOT NULL,
                external_id VARCHAR(100),
                change_type VARCHAR(50) NOT NULL,
                field_name VARCHAR(100),
                old_value TEXT,
                new_value TEXT,
                source_url VARCHAR(1000),
                scrape_run_id INTEGER,
                metadata_json JSON,
                detected_at DATETIME NOT NULL,
                notified_at DATETIME,
                created_at DATETIME NOT NULL
            )
            """
        )
        # Insert pre-existing row
        cur.execute(
            """
            INSERT INTO change_events (
                entity_type, entity_id, external_id, change_type, old_value, new_value,
                detected_at, created_at
            ) VALUES (
                'MATCH', 101, 'match-legacy-101', 'UPDATED', 'OLD_SCORE', 'NEW_SCORE',
                '2026-10-01 10:00:00', '2026-10-01 10:00:00'
            )
            """
        )
        con.commit()
        con.close()

        # 2. Run init_db which triggers _upgrade_schema
        engine = create_engine(f"sqlite:///{db_path}")
        init_db(engine)

        # 3. Verify 'severity' was added
        inspector = inspect(engine)
        ce_columns = {col["name"] for col in inspector.get_columns("change_events")}
        assert "severity" in ce_columns

        # 4. Verify existing row is preserved and has default severity
        with Session(engine) as session:
            stmt = select(ChangeEvent).where(ChangeEvent.entity_id == 101)
            event = session.scalars(stmt).first()
            assert event is not None
            assert event.external_id == "match-legacy-101"
            assert event.old_value == "OLD_SCORE"
            assert event.new_value == "NEW_SCORE"
            assert event.severity == "INFO"

    def test_idempotent_multiple_initializations(self, tmp_path):
        db_path = tmp_path / "idempotent.db"
        engine = create_engine(f"sqlite:///{db_path}")

        # First run
        init_db(engine)
        # Second run
        init_db(engine)
        # Third run
        init_db(engine)

        inspector = inspect(engine)
        ce_columns = {col["name"] for col in inspector.get_columns("change_events")}
        assert "severity" in ce_columns

    def test_notification_and_change_detection_queries_after_upgrade(self, tmp_path):
        db_path = tmp_path / "notif_query.db"
        engine = create_engine(f"sqlite:///{db_path}")

        init_db(engine)

        with Session(engine) as session:
            # Seed change event
            ce = ChangeEvent(
                entity_type="MATCH",
                entity_id=202,
                external_id="match-202",
                change_type="STATUS_CHANGED",
                field_name="status",
                old_value="UPCOMING",
                new_value="LIVE",
                severity="CRITICAL",
                detected_at=utc_now(),
            )
            session.add(ce)
            session.commit()

            # Verify NotificationRepository query runs cleanly without OperationalError
            repo = NotificationRepository(session)
            unnotified = repo.get_unnotified_events()
            assert len(unnotified) == 1
            assert unnotified[0].severity == "CRITICAL"

            # Verify ChangeDetector query runs cleanly
            detector = ChangeDetector(session)
            det_res = detector.detect_all(matches_data=[])
            assert det_res is not None
