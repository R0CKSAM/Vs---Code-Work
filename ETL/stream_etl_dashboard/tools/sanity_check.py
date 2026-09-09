"""End-to-end sanity checks for the running ETL dashboard."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8788"
DB = ROOT / "data" / "analytics.db"
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    marker = "PASS" if condition else "FAIL"
    print(f"[{marker}] {message}")
    if not condition:
        failures.append(message)


def fetch(path: str) -> tuple[int, bytes, str]:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return response.status, response.read(), response.headers.get("content-type", "")


def fetch_json(path: str) -> dict:
    status, body, content_type = fetch(path)
    check(status == 200, f"GET {path} returns HTTP 200")
    check("application/json" in content_type, f"GET {path} returns JSON")
    return json.loads(body)


def database_checks() -> None:
    check(DB.exists() and DB.stat().st_size > 0, "SQLite database exists and is non-empty")
    connection = sqlite3.connect(DB)
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    check(integrity == "ok", "SQLite integrity_check is OK")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check({"ingested_objects", "minute_clients", "pipeline_status"} <= tables, "Required database tables exist")
    for stream in ("vglive-274906", "upgovlive"):
        rows, requests, first, last = connection.execute(
            """SELECT COUNT(*), COALESCE(SUM(requests),0), MIN(minute), MAX(minute)
               FROM minute_clients WHERE stream=?""", (stream,)
        ).fetchone()
        check(rows > 0, f"{stream} has database minute/client rows ({rows:,})")
        check(requests > 0, f"{stream} has requests ({requests:,})")
        print(f"       range: {first} -> {last}")
    failed = connection.execute("SELECT COUNT(*) FROM ingested_objects WHERE status='failed'").fetchone()[0]
    completed = connection.execute("SELECT COUNT(*) FROM ingested_objects WHERE status='completed'").fetchone()[0]
    check(completed > 0, f"Pipeline has completed objects ({completed:,})")
    check(failed == 0, f"Pipeline has no failed objects (found {failed:,})")
    connection.close()


def http_checks() -> None:
    status, page, content_type = fetch("/")
    html = page.decode("utf-8")
    check(status == 200 and "text/html" in content_type, "Dashboard HTML is served")
    for element_id in ("concurrencyChart", "minutes", "geography", "pipeline", "streamButtons"):
        check(f'id="{element_id}"' in html, f"Dashboard contains #{element_id}")
    for asset in ("/static/style.css", "/static/app.js", "/static/chart.umd.min.js"):
        asset_status, body, _ = fetch(asset)
        check(asset_status == 200 and len(body) > 100, f"Asset {asset} loads ({len(body):,} bytes)")

    streams = fetch_json("/api/streams").get("streams", [])
    check(set(streams) == {"vglive-274906", "upgovlive"}, "API exposes both expected dashboard streams")
    health = fetch_json("/api/health")
    check("status" in health and "objects" in health and "lag_seconds" in health, "Health payload is complete")
    check(health.get("lag_seconds") is not None and health["lag_seconds"] < 120, "Data freshness is below two minutes")
    check(health["status"].get("sync_status") not in {"Error", "Fatal"}, "Sync status is healthy")
    print(f"       sync={health['status'].get('sync_status')} lag={health.get('lag_seconds')}s")

    for stream in streams:
        for hours in (1, 3, 6, 24):
            minutes = fetch_json(f"/api/minutes?stream={stream}&hours={hours}")
            check(isinstance(minutes.get("rows"), list), f"{stream} {hours}h minute payload has rows array")
            if hours == 24:
                check(len(minutes["rows"]) > 0, f"{stream} full-day minute table has data ({len(minutes['rows'])} rows)")
                if minutes["rows"]:
                    required = {"minute", "viewers", "requests", "errors_4xx", "errors_5xx", "status"}
                    check(required <= minutes["rows"][0].keys(), f"{stream} minute rows contain every dashboard field")
        summary = fetch_json(f"/api/summary?stream={stream}&hours=24")
        check(summary.get("requests", 0) > 0, f"{stream} summary contains requests")
        geography = fetch_json(f"/api/geography?stream={stream}&hours=24")
        check(isinstance(geography.get("rows"), list), f"{stream} geography payload is valid")
        csv_status, csv_body, csv_type = fetch(f"/api/export.csv?stream={stream}&hours=24")
        csv_rows = list(csv.DictReader(io.StringIO(csv_body.decode("utf-8"))))
        check(csv_status == 200 and "text/csv" in csv_type and len(csv_rows) > 0, f"{stream} CSV export works ({len(csv_rows)} rows)")

    pipeline = fetch_json("/api/pipeline?limit=10")
    check(len(pipeline.get("rows", [])) > 0, "Pipeline table API returns rows")


database_checks()
http_checks()
print("\nRESULT:", "PASS" if not failures else f"FAIL ({len(failures)} checks)")
if failures:
    for failure in failures:
        print(" -", failure)
    sys.exit(1)
