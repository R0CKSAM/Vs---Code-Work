"""
test_observability_diagnostics.py – Unit tests for DB integrity and operational diagnostics (Phase 11).
"""

from __future__ import annotations

import pytest
from app.observability.diagnostics import (
    check_database_integrity,
    collect_system_diagnostics,
    format_diagnostics_text,
)


class TestDatabaseIntegrityAndDiagnostics:
    def test_database_integrity_healthy_schema(self, db_session):
        result = check_database_integrity(session=db_session)

        assert result["status"] == "OK"
        assert result["connection"] == "OK"
        assert result["read_test"] == "OK"
        assert len(result["tables_missing"]) == 0
        assert len(result["tables_found"]) >= 7

    def test_collect_system_diagnostics(self, db_session):
        diag = collect_system_diagnostics(session=db_session)

        assert diag["status"] == "HEALTHY"
        assert "database_integrity" in diag
        assert "metrics" in diag
        assert diag["database_integrity"]["status"] == "OK"

    def test_format_diagnostics_text(self, db_session):
        diag = collect_system_diagnostics(session=db_session)
        text = format_diagnostics_text(diag)

        assert "FanCode Monitor — Operational Diagnostics" in text
        assert "Overall Status       : HEALTHY" in text
        assert "Database Connection  : OK" in text
        assert "In-Process Operational Metrics:" in text
