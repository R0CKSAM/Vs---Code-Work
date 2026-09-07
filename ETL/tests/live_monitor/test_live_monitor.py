from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

from ETL.src.live_monitor.parser import IST, parse_gzip_file, query_identifiers
from ETL.src.live_monitor.config import LiveConfig
from ETL.src.live_monitor.engine import LiveEngine
from ETL.src.live_monitor.store import LiveStore
from ETL.src.live_monitor.server import SnapshotServer
from ETL.src.live_monitor.s3_index import load_rclone_s3_remote


def write_log(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def test_parser_builds_exact_minute_metrics_without_storing_raw_ip(tmp_path: Path) -> None:
    path = tmp_path / "sample.gz"
    timestamp = dt.datetime(2026, 9, 4, 10, 15, tzinfo=IST).timestamp()
    write_log(
        path,
        [
            {
                "reqTimeSec": timestamp,
                "reqHost": "veto.akamaized.net",
                "reqPath": "v1/vglive-sk-274906/chunk.ts",
                "cliIP": "192.0.2.10",
                "statusCode": 503,
                "bytes": 100,
                "queryStr": "device_id=device-123&session_id=session-456",
                "cacheStatus": "1",
                "country": "IN",
                "city": "Delhi",
                "asn": "AS123",
                "UA": "Mozilla/5.0 (SMART-TV; Linux; Tizen 7.0)",
                "deliveryFormat": "HLS",
            },
            {
                "reqTimeSec": timestamp + 20,
                "reqHost": "veto.akamaized.net",
                "reqPath": "v1/vglive-sk-274906/chunk-2.ts",
                "cliIP": "192.0.2.10",
                "statusCode": 200,
                "bytes": 200,
                "queryStr": "device_id=device-123&session_id=session-456",
            },
        ],
    )

    batch = parse_gzip_file(path, ("vglive-274906",))

    watched = next(value for key, value in batch.metrics.items() if key[2] == "India TV")
    assert watched == [2, 300, 0, 1, 2]
    assert len([row for row in batch.minute_viewers if row[2] == "India TV"]) == 1
    assert all("192.0.2.10" not in row for row in batch.minute_viewers)
    assert len([row for row in batch.minute_devices if row[2] == "India TV"]) == 1
    assert len([row for row in batch.minute_sessions if row[2] == "India TV"]) == 1
    assert all("device-123" not in row for row in batch.minute_devices)
    assert all("session-456" not in row for row in batch.minute_sessions)
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "cache", "Hit")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "device_inferred", "Samsung/Tizen TV")][0] == 1


def test_query_identifiers_supports_fully_encoded_query_strings() -> None:
    assert query_identifiers(
        "device_id%3Ddevice-123%26session_id%3Dsession-456"
    ) == ("device-123", "session-456")
    assert query_identifiers("-") == ("", "")


def test_store_commits_file_and_aggregates_in_one_transaction(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"content")
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    assert store.claim_file() == source.resolve()

    from ETL.src.live_monitor.parser import FileBatch

    batch = FileBatch(rows=1, latest_timestamp=1_788_500_000)
    batch.metrics[("2026-09-04T10:15:00+0530", "host", "__all__")] = [1, 50, 0, 0, 1]
    batch.minute_viewers.add(("2026-09-04T10:15:00+0530", "host", "__all__", "hash"))
    batch.minute_devices.add(("2026-09-04T10:15:00+0530", "host", "__all__", "device-hash"))
    batch.minute_sessions.add(("2026-09-04T10:15:00+0530", "host", "__all__", "session-hash"))
    batch.dimensions[("2026-09-04T10:15:00+0530", "host", "__all__", "status", "2xx")] = [1, 50]
    batch.daily_viewers.add(("2026-09-04", "host", "__all__", "hash"))
    store.finish_file(source, batch)

    assert store.claim_file() is None
    snapshot = store.snapshot(10_000_000)
    assert snapshot["files"] == {"done": 1}
    assert snapshot["rows"] == 1
    assert snapshot["series"]["__all__"][0]["active_cliips"] == 1
    assert snapshot["series"]["__all__"][0]["device_ids"] == 1
    assert snapshot["series"]["__all__"][0]["session_ids"] == 1
    assert snapshot["summaries"]["__all__"]["unique_cliips"] == 1
    assert snapshot["summaries"]["__all__"]["estimated_watch_seconds"] == 6
    assert snapshot["breakdowns"]["__all__"]["status"][0]["value"] == "2xx"


def test_restart_requeues_interrupted_file_immediately(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"content")
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    assert store.claim_file() == source.resolve()

    assert store.recover(300) == 1
    assert store.claim_file() == source.resolve()


def test_completed_file_change_is_not_double_counted(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"old")
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    claimed = store.claim_file()
    assert claimed is not None

    from ETL.src.live_monitor.parser import FileBatch

    store.finish_file(claimed, FileBatch(rows=1))
    source.write_bytes(b"new content")
    stat = source.stat()

    assert store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1) == "changed"
    assert store.claim_file() is None


def test_snapshot_server_serves_only_valid_atomic_json(tmp_path: Path) -> None:
    snapshot = tmp_path / "live_state.json"
    snapshot.write_text('{"series":{}}', encoding="utf-8")
    server = SnapshotServer("127.0.0.1", 0, snapshot)
    server.start()
    try:
        port = server.httpd.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2) as response:
            assert json.load(response) == {"series": {}}
            assert response.headers["Cache-Control"] == "no-store"
        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            page = response.read().decode("utf-8")
            assert 'id="minuteRows"' in page
            assert 'id="yAxis"' in page
            assert 'id="chartScroll"' in page
            assert 'id="tooltip"' in page
            assert "15 MIN TICKS" in page
            assert "function channelRows(key)" in page
            assert "VETO Live Audience &amp; CDN Operations" in page
            assert "Known device IDs" in page
            assert "Known session IDs" in page
            assert "drawing=false" in page
            assert "AUDIENCE GEOGRAPHY" in page
            assert "CDN TRAFFIC &amp; CACHE" in page
    finally:
        server.stop()


def test_snapshot_server_reports_degraded_health(tmp_path: Path) -> None:
    snapshot = tmp_path / "live_state.json"
    snapshot.write_text(
        '{"health":{"ok":false,"status":"degraded","issues":["late"]}}',
        encoding="utf-8",
    )
    server = SnapshotServer("127.0.0.1", 0, snapshot)
    server.start()
    try:
        port = server.httpd.server_address[1]
        try:
            urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)
            raise AssertionError("degraded health unexpectedly returned HTTP 200")
        except HTTPError as exc:
            assert exc.code == 503
            assert json.load(exc)["status"] == "degraded"
    finally:
        server.stop()


def test_unchanged_flat_directory_is_not_walked_repeatedly(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    day = spool / "09-04-2026"
    day.mkdir(parents=True)
    source = day / "one.gz"
    write_log(source, [])
    config = LiveConfig(spool_root=spool, state_dir=tmp_path / "state")
    engine = LiveEngine(config, sync_enabled=False)

    assert engine.scan_directories([day]) == 1
    assert engine.scan_directories([day]) == 0
    assert engine.store.snapshot(10)["files"] == {"pending": 1}


def test_forced_scan_reconciles_an_unchanged_directory(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    day = spool / "09-04-2026"
    day.mkdir(parents=True)
    source = day / "one.gz"
    write_log(source, [])
    config = LiveConfig(spool_root=spool, state_dir=tmp_path / "state")
    engine = LiveEngine(config, sync_enabled=False)

    assert engine.scan_directories([day]) == 1
    assert engine.scan_directories([day], force=True) == 0


def test_restart_uses_durable_file_signatures(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    day = spool / "09-04-2026"
    day.mkdir(parents=True)
    source = day / "one.gz"
    write_log(source, [])
    config = LiveConfig(spool_root=spool, state_dir=tmp_path / "state")
    first = LiveEngine(config, sync_enabled=False)
    assert first.scan_directories([day]) == 1

    restarted = LiveEngine(config, sync_enabled=False)

    assert restarted.scan_directories([day]) == 0


def test_recent_sync_uses_exact_s3_keys_and_backfill_uses_yesterday(
    tmp_path: Path, monkeypatch,
) -> None:
    config = LiveConfig(spool_root=tmp_path / "spool", state_dir=tmp_path / "state")
    engine = LiveEngine(config)
    calls = []

    monkeypatch.setattr(
        "ETL.src.live_monitor.engine.list_recent_relative_keys",
        lambda _remote, _hours, local_root=None: ["ak-000001-sample.gz"],
    )

    def fake_rclone(
        remote, local, timeout, max_age=None, min_age=None, files_from=None,
    ):
        calls.append((remote, local, timeout, max_age, min_age, files_from))
        return True

    engine._rclone = fake_rclone
    assert engine.sync_once()
    recent_calls = list(calls)
    calls.clear()
    assert engine.backfill_once()

    assert recent_calls
    assert all(call[3] is None and call[4] is None and call[5] for call in recent_calls)
    assert len(calls) == 1
    assert calls[0][3] is None and calls[0][4] is None and calls[0][5] is None
    yesterday = dt.datetime.now(IST) - dt.timedelta(days=1)
    assert calls[0][0].endswith(yesterday.strftime("/%m/%d"))


def test_rclone_s3_config_is_loaded_without_exposing_credentials(
    tmp_path: Path, monkeypatch,
) -> None:
    config_path = tmp_path / "rclone.conf"
    config_path.write_text(
        "[sample]\n"
        "type = s3\n"
        "endpoint = objects.example.test\n"
        "region = test-1\n"
        "access_key_id = access\n"
        "secret_access_key = secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RCLONE_CONFIG", str(config_path))

    remote = load_rclone_s3_remote("sample:bucket/path/to/day")

    assert remote.bucket == "bucket"
    assert remote.key_prefix == "path/to/day"
    assert remote.endpoint == "https://objects.example.test"
