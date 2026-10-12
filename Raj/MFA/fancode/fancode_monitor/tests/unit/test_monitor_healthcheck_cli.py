from __future__ import annotations

import sys

import run_monitor


def test_healthcheck_cli_returns_nonzero_when_any_check_fails(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_monitor.py", "--healthcheck", "--json"])
    monkeypatch.setattr(run_monitor, "init_db", lambda: None)
    monkeypatch.setattr(
        run_monitor,
        "run_healthcheck",
        lambda: {"status": "FAIL", "checks": {"database": {"ok": False}}},
    )
    assert run_monitor.main() != 0


def test_healthcheck_cli_returns_zero_when_all_checks_pass(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_monitor.py", "--healthcheck", "--json"])
    monkeypatch.setattr(run_monitor, "init_db", lambda: None)
    monkeypatch.setattr(
        run_monitor,
        "run_healthcheck",
        lambda: {"status": "PASS", "checks": {"database": {"ok": True}}},
    )
    assert run_monitor.main() == 0
