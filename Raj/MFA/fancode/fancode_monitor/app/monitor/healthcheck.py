"""Deep, side-effect-minimized operational healthcheck for the monitor CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from app.config.settings import settings
from app.config.validation import validate_settings
from app.database.connection import create_db_engine
from app.monitor.lock import MonitorLock
from app.notifications.smtp_test import create_smtp_backend


def run_healthcheck() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    config_errors = validate_settings()
    checks["config"] = {"ok": not config_errors, "errors": config_errors}

    try:
        engine = create_db_engine()
        with engine.connect() as connection:
            integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar_one()
            foreign_key_violations = list(connection.exec_driver_sql("PRAGMA foreign_key_check"))
        engine.dispose()
        checks["database"] = {
            "ok": integrity == "ok" and not foreign_key_violations,
            "integrity": integrity,
            "foreign_key_violations": len(foreign_key_violations),
        }
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    try:
        lock = MonitorLock()
        acquired = lock.acquire(blocking=False)
        checks["lock"] = {"ok": acquired, "status": "available" if acquired else "active"}
        if acquired:
            lock.release()
    except Exception as exc:
        checks["lock"] = {"ok": False, "error": str(exc)}

    try:
        heartbeat_path = Path(settings.HEARTBEAT_FILE)
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=heartbeat_path.parent, delete=True
        ) as probe:
            json.dump({"healthcheck": True}, probe)
            probe.flush()
        checks["heartbeat"] = {"ok": True, "path": str(heartbeat_path)}
    except Exception as exc:
        checks["heartbeat"] = {"ok": False, "error": str(exc)}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        checks["playwright"] = {"ok": True, "browser": "chromium"}
    except Exception as exc:
        checks["playwright"] = {"ok": False, "error": str(exc)}

    smtp_required = bool(settings.SMTP_ENABLED or settings.EMAIL_BACKEND.lower() == "smtp")
    if smtp_required:
        try:
            create_smtp_backend().verify_connection()
            checks["smtp"] = {"ok": True, "mode": "authenticated"}
        except Exception as exc:
            checks["smtp"] = {"ok": False, "error": str(exc)}
    else:
        checks["smtp"] = {"ok": True, "mode": "disabled"}

    ok = all(check.get("ok", False) for check in checks.values())
    return {"status": "PASS" if ok else "FAIL", "checks": checks}
