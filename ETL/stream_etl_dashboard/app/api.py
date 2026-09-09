from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import connect, initialize


IST = timezone(timedelta(hours=5, minutes=30))
app = FastAPI(title="Stream ETL Dashboard")
STATIC = settings.project_root / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


def valid_stream(stream: str) -> str:
    if stream not in settings.streams:
        raise HTTPException(400, "Unknown stream")
    return stream


def cutoff(hours: int) -> str:
    return (datetime.now(IST) - timedelta(hours=hours)).replace(second=0, microsecond=0).isoformat()


@app.get("/api/streams")
def streams():
    return {"streams": settings.streams}


@app.get("/api/health")
def health():
    with connect() as conn:
        status = {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM pipeline_status")}
        counts = conn.execute(
            "SELECT COUNT(*) total, SUM(status='completed') completed, SUM(status='failed') failed FROM ingested_objects"
        ).fetchone()
    latest = status.get("latest_event_at")
    lag = None
    if latest:
        lag = max(0, int((datetime.now(IST) - datetime.fromisoformat(latest)).total_seconds()))
    return {"status": status, "objects": dict(counts), "lag_seconds": lag}


SUMMARY_SQL = """
SELECT minute, COUNT(DISTINCT client_ip) viewers, SUM(requests) requests,
       SUM(errors_4xx) errors_4xx, SUM(errors_5xx) errors_5xx
FROM minute_clients WHERE stream=? AND minute>=?
GROUP BY minute ORDER BY minute
"""


@app.get("/api/minutes")
def minutes(stream: str, hours: int = Query(1, ge=1, le=24)):
    valid_stream(stream)
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(SUMMARY_SQL, (stream, cutoff(hours)))]
    boundary = datetime.now(IST) - timedelta(seconds=settings.finalize_after_seconds)
    for row in rows:
        row["status"] = "Final" if datetime.fromisoformat(row["minute"]) < boundary else "Partial"
    return {"stream": stream, "hours": hours, "rows": rows}


@app.get("/api/summary")
def summary(stream: str, hours: int = Query(24, ge=1, le=24)):
    payload = minutes(valid_stream(stream), hours)["rows"]
    final = [r for r in payload if r["status"] == "Final"]
    current = final[-1] if final else (payload[-1] if payload else None)
    return {
        "current_viewers": current["viewers"] if current else 0,
        "peak_viewers": max((r["viewers"] for r in payload), default=0),
        "requests": sum(r["requests"] for r in payload),
        "errors_4xx": sum(r["errors_4xx"] for r in payload),
        "errors_5xx": sum(r["errors_5xx"] for r in payload),
    }


@app.get("/api/geography")
def geography(stream: str, hours: int = Query(24, ge=1, le=24)):
    valid_stream(stream)
    sql = """SELECT state, COUNT(DISTINCT client_ip) viewers, SUM(requests) requests
             FROM minute_clients WHERE stream=? AND minute>=? GROUP BY state ORDER BY viewers DESC"""
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, (stream, cutoff(hours)))]
    total = sum(r["requests"] for r in rows) or 1
    for row in rows:
        row["percentage"] = round(row["requests"] * 100 / total, 2)
    return {"rows": rows}


@app.get("/api/pipeline")
def pipeline(limit: int = Query(100, ge=1, le=500)):
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM ingested_objects ORDER BY processed_at DESC LIMIT ?", (limit,)
        )]
    return {"rows": rows}


@app.get("/api/export.csv")
def export_csv(stream: str, hours: int = Query(24, ge=1, le=24)):
    rows = minutes(valid_stream(stream), hours)["rows"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["minute", "viewers", "requests", "errors_4xx", "errors_5xx", "status"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{stream}.csv"'})

