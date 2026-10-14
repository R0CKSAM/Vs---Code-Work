import datetime as dt
import json

import pytest

from ETL.src.live_monitor.config import LiveConfig
from ETL.src.live_monitor.engine import InstanceLock
from ETL.src.live_monitor.parser import FileBatch, IST
from ETL.src.live_monitor.store import LiveStore


NOW = dt.datetime(2026, 10, 14, 17, tzinfo=IST)
OLD = "2026-10-06T23:59:00+0530"
BOUNDARY = "2026-10-07T00:00:00+0530"
TODAY = "2026-10-14T12:00:00+0530"


def ingest(store, tmp_path, name, minutes):
    path = tmp_path / name
    path.write_bytes(b"source must remain")
    store.observe_file(path, path.stat().st_size, path.stat().st_mtime_ns, 1)
    assert store.claim_file() == path.resolve()
    batch = FileBatch(rows=len(minutes), latest_timestamp=max(
        dt.datetime.strptime(minute, "%Y-%m-%dT%H:%M:%S%z").timestamp() for minute in minutes
    ))
    for minute in minutes:
        batch.metrics[(minute, "host", "channel")] = [1, 100, 0, 0, 1] + [0] * 11
        for attr in ("minute_viewers", "minute_devices", "minute_sessions"):
            getattr(batch, attr).add((minute, "host", "channel", minute))
        batch.daily_viewers.add((minute[:10], "host", "channel", minute))
        batch.dimensions[(minute, "host", "channel", "region", "IN")] = [1, 100]
        batch.quality_dimensions[(minute, "host", "channel", "region", "IN")] = [1] + [0] * 8
    store.finish_file(path, batch)
    return path


def test_retention_boundary_all_tables_and_late_replay(tmp_path):
    store = LiveStore(tmp_path / "monitor.sqlite3")
    source = ingest(store, tmp_path, "mixed.gz", [OLD, BOUNDARY, TODAY])
    result = store.prune_history(now=NOW, batch_size=1)
    assert result["complete"]
    assert result["cutoff_ist"] == BOUNDARY
    assert source.exists()
    for table in ("minute_metrics", "minute_viewers", "minute_devices", "minute_sessions",
                  "minute_dimensions", "minute_quality_dimensions", "daily_viewers", "viewer_history"):
        with store.connect(write=False) as conn:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 2
    ingest(store, tmp_path, "late.gz", [OLD, BOUNDARY])
    with store.connect(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) FROM minute_metrics WHERE minute_ist < ?", (BOUNDARY,)).fetchone()[0] == 0
        assert conn.execute("SELECT requests FROM minute_metrics WHERE minute_ist=?", (BOUNDARY,)).fetchone()[0] == 2
    assert store.observe_file(source, source.stat().st_size, source.stat().st_mtime_ns, 1) == "done"


def test_only_old_completed_ledger_removed_and_watermark_never_regresses(tmp_path):
    store = LiveStore(tmp_path / "monitor.sqlite3")
    source = ingest(store, tmp_path, "old.gz", [OLD])
    with store.connect() as conn:
        conn.execute("UPDATE files SET updated_at=0")
        for state in ("pending", "processing", "failed", "changed", "observed"):
            conn.execute("""INSERT INTO files(path,size,mtime_ns,status,discovered_at,updated_at,max_event_ts)
                VALUES(?,1,1,?,0,0,1)""", (state, state))
    assert store.prune_history(now=NOW)["complete"]
    with store.connect(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) FROM files WHERE status='done'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 5
    assert source.exists()
    assert store.prune_history(now=NOW - dt.timedelta(days=2))["cutoff_ist"] == BOUNDARY


def test_interrupted_cleanup_is_resumable(tmp_path):
    import threading
    store = LiveStore(tmp_path / "monitor.sqlite3")
    ingest(store, tmp_path, "old.gz", [OLD])
    stop = threading.Event()
    stop.set()
    assert not store.prune_history(now=NOW, stop_event=stop)["complete"]
    assert store.prune_history(now=NOW)["complete"]
    with store.connect(write=False) as conn:
        result = json.loads(conn.execute("SELECT value FROM metadata WHERE key='retention_last_result'").fetchone()[0])
    assert result["complete"]


def test_defaults_and_instance_lock(tmp_path, monkeypatch):
    monkeypatch.delenv("VETO_LIVE_RETENTION_DAYS", raising=False)
    assert LiveConfig().retention_days == 7
    with InstanceLock(tmp_path / "monitor.lock"):
        with pytest.raises(RuntimeError, match="already running"):
            with InstanceLock(tmp_path / "monitor.lock"):
                pass


def test_utc_clock_uses_ist_calendar_boundary(tmp_path):
    store = LiveStore(tmp_path / "monitor.sqlite3")
    utc = dt.datetime(2026, 10, 13, 20, tzinfo=dt.timezone.utc)
    assert store.prune_history(now=utc)["cutoff_ist"] == BOUNDARY


def test_cleanup_resumes_at_saved_table(tmp_path):
    store = LiveStore(tmp_path / "monitor.sqlite3")
    ingest(store, tmp_path, "old.gz", [OLD])
    with store.connect() as conn:
        conn.execute("DELETE FROM minute_metrics")
        conn.execute("INSERT INTO metadata VALUES('retention_last_result',?)", (json.dumps({
            "cutoff_ist": BOUNDARY, "complete": False, "next_table": "minute_viewers"
        }),))
    result = store.prune_history(now=NOW)
    assert result["complete"]
    assert "minute_metrics" not in result["deleted"]
    assert result["deleted"]["minute_viewers"] == 1
