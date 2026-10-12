"""
test_error_classification.py – Unit tests for error categorization and action resolution (Phase 11).
"""

from __future__ import annotations

from app.monitor.exceptions import (
    ErrorAction,
    ErrorCategory,
    LockAcquisitionError,
    LockError,
    StageExecutionError,
    StageTimeoutError,
    classify_error,
)


class TestErrorClassification:
    def test_classify_keyboard_interrupt(self):
        cat, act = classify_error(KeyboardInterrupt())
        assert cat == ErrorCategory.INTERRUPTION
        assert act == ErrorAction.ABORT

    def test_classify_lock_errors(self):
        cat1, act1 = classify_error(LockAcquisitionError("Lock active"))
        assert cat1 == ErrorCategory.LOCK_ERROR
        assert act1 == ErrorAction.ABORT

        cat2, act2 = classify_error(LockError("Generic lock error"))
        assert cat2 == ErrorCategory.LOCK_ERROR
        assert act2 == ErrorAction.ABORT

    def test_classify_network_and_timeout_errors(self):
        cat1, act1 = classify_error(ConnectionResetError("Socket reset"))
        assert cat1 == ErrorCategory.NETWORK_ERROR
        assert act1 == ErrorAction.RETRY

        cat2, act2 = classify_error(StageTimeoutError("Stage timed out"))
        assert cat2 == ErrorCategory.TIMEOUT_ERROR
        assert act2 == ErrorAction.RETRY

    def test_classify_database_errors(self):
        class OperationalError(Exception):
            pass

        cat, act = classify_error(OperationalError("database locked"))
        assert cat == ErrorCategory.DATABASE_ERROR
        assert act == ErrorAction.ABORT

    def test_classify_unknown_error(self):
        cat, act = classify_error(ValueError("Some invalid argument"))
        assert cat == ErrorCategory.UNKNOWN_ERROR
        assert act == ErrorAction.CONTINUE
