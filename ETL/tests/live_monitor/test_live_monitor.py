from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

from ETL.src.live_monitor.parser import (
    IST,
    inferred_resolution,
    parse_gzip_file,
    query_identifiers,
)
from ETL.src.live_monitor.enrichment import decoded_asn_dimensions, normalize_ua
from ETL.src.live_monitor.config import LiveConfig
from ETL.src.live_monitor.engine import LiveEngine, atomic_write_json
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
                "deliveryFormat": "1",
                "deliveryType": "1",
                "mediaEncryption": "1",
                "timeToFirstByte": "80",
                "turnAroundTimeMSec": "60",
                "transferTimeMSec": "20",
                "throughput": "1500.5",
                "tlsOverheadTimeMSec": "4",
                "tlsVersion": "TLSv1.3",
                "cacheable": "1",
                "edgeAttempts": "2",
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
    assert watched == [2, 300, 0, 1, 2, 1, 80.0, 1, 60.0, 1, 20.0, 1, 1500.5, 1, 4.0, 1]
    assert len([row for row in batch.minute_viewers if row[2] == "India TV"]) == 1
    assert all("192.0.2.10" not in row for row in batch.minute_viewers)
    assert len([row for row in batch.minute_devices if row[2] == "India TV"]) == 1
    assert len([row for row in batch.minute_sessions if row[2] == "India TV"]) == 1
    assert all("device-123" not in row for row in batch.minute_devices)
    assert all("session-456" not in row for row in batch.minute_sessions)
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "cache", "Cache hit - child edge")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "device_inferred", "Samsung/Tizen TV")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "tls_version", "TLSv1.3")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "delivery_format", "Apple / HLS")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "delivery_type", "Adaptive media - live")][0] == 1
    assert batch.dimensions[("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "media_encryption", "Enabled")][0] == 1
    cache_quality = batch.quality_dimensions[
        ("2026-09-04T10:15:00+0530", "veto.akamaized.net", "India TV", "cache", "Cache hit - child edge")
    ]
    assert cache_quality == [1, 0, 1, 1, 80.0, 1, 60.0, 1, 1500.5]


def test_query_identifiers_supports_fully_encoded_query_strings() -> None:
    assert query_identifiers(
        "device_id%3Ddevice-123%26session_id%3Dsession-456"
    ) == ("device-123", "session-456")
    assert query_identifiers("-") == ("", "")


def test_resolution_inference_requires_resolution_evidence_in_path() -> None:
    assert inferred_resolution("channel/live_216p/chunks.m3u8") == "216p"
    assert inferred_resolution("asset_1920x1080_42.ts") == "1080p"
    assert inferred_resolution("channel/720p60/segment.m4s") == "720p"
    assert inferred_resolution("channel/main_1_10714360.ts") == "Unknown"
    assert inferred_resolution("channel/main_10.m3u8") == "Unknown"


def test_live_enrichment_normalizes_ua_and_resolves_asn_cache() -> None:
    assert normalize_ua("Mozilla%252F5.0%2520Test") == "Mozilla/5.0 Test"
    decoded = decoded_asn_dimensions("AS55836")
    assert decoded["network_provider"] == "Reliance Jio Infocomm Limited"
    assert decoded["network_type"] == "(MOB) Mobile ISP"


def test_store_commits_file_and_aggregates_in_one_transaction(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"content")
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    assert store.claim_file() == source.resolve()

    from ETL.src.live_monitor.parser import FileBatch

    batch = FileBatch(rows=1, latest_timestamp=1_788_500_000)
    batch.metrics[("2026-09-04T10:15:00+0530", "host", "__all__")] = [
        1, 50, 0, 0, 1, 1, 25, 1, 20, 1, 5, 1, 1800, 1, 2, 0
    ]
    batch.minute_viewers.add(("2026-09-04T10:15:00+0530", "host", "__all__", "hash"))
    batch.minute_devices.add(("2026-09-04T10:15:00+0530", "host", "__all__", "device-hash"))
    batch.minute_sessions.add(("2026-09-04T10:15:00+0530", "host", "__all__", "session-hash"))
    batch.dimensions[("2026-09-04T10:15:00+0530", "host", "__all__", "status", "2xx")] = [1, 50]
    batch.dimensions[
        ("2026-09-04T10:15:00+0530", "host", "__all__", "network_provider", "Example ISP")
    ] = [10, 1000]
    batch.quality_dimensions[
        ("2026-09-04T10:15:00+0530", "host", "__all__", "network_provider", "Example ISP")
    ] = [10, 1, 2, 2, 80, 2, 60, 2, 3000]
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
    assert snapshot["summaries"]["__all__"]["new_cliips"] == 1
    assert snapshot["summaries"]["__all__"]["returning_cliips"] == 0
    assert snapshot["summaries"]["__all__"]["estimated_watch_seconds"] == 6
    assert snapshot["summaries"]["__all__"]["ttfb_avg_ms"] == 25
    assert snapshot["series"]["__all__"][0]["throughput_avg"] == 1800
    assert snapshot["breakdowns"]["__all__"]["status"][0]["value"] == "2xx"
    provider = snapshot["breakdowns"]["__all__"]["network_provider"][0]
    assert provider["value"] == "Example ISP"
    assert provider["errors_4xx"] == 1
    assert provider["errors_5xx"] == 2
    assert provider["quality_requests"] == 10
    assert provider["ttfb_avg_ms"] == 40
    assert provider["turnaround_avg_ms"] == 30
    assert provider["throughput_avg"] == 1500


def test_store_migrates_legacy_cdn_dimension_labels(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    store = LiveStore(database)
    with store.connect() as connection:
        connection.execute(
            "DELETE FROM metadata WHERE key='dimension_labels_v2'"
        )
        connection.execute(
            """
            INSERT INTO minute_dimensions(
                minute_ist,req_host,target,dimension,value,requests,bytes
            ) VALUES(?,?,?,?,?,?,?)
            """,
            ("2026-09-04T10:15:00+0530", "host", "__all__", "cache", "Hit", 3, 30),
        )
        connection.execute(
            """
            INSERT INTO minute_dimensions(
                minute_ist,req_host,target,dimension,value,requests,bytes
            ) VALUES(?,?,?,?,?,?,?)
            """,
            ("2026-09-04T10:15:00+0530", "host", "__all__", "cache", "Cache hit - child edge", 2, 20),
        )
        connection.execute(
            """
            INSERT INTO minute_dimensions(
                minute_ist,req_host,target,dimension,value,requests,bytes
            ) VALUES(?,?,?,?,?,?,?)
            """,
            ("2026-09-04T10:15:00+0530", "host", "__all__", "delivery_format", "1", 5, 50),
        )

    migrated = LiveStore(database).snapshot(10_000_000)
    cache = migrated["breakdowns"]["__all__"]["cache"]
    delivery_format = migrated["breakdowns"]["__all__"]["delivery_format"]
    assert [(row["value"], row["requests"], row["bytes"]) for row in cache] == [
        ("Cache hit - child edge", 5, 50)
    ]
    assert [
        (row["value"], row["requests"], row["bytes"])
        for row in delivery_format
    ] == [("Apple / HLS", 5, 50)]


def test_new_and_returning_ip_viewers_are_mutually_exclusive(tmp_path: Path) -> None:
    store = LiveStore(tmp_path / "state.sqlite3")
    now = dt.datetime.now(IST).replace(second=0, microsecond=0)
    old_minute = (now - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:00%z")
    recent_minute = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:00%z")

    def finish(name: str, minute: str, viewers: tuple[str, ...]) -> None:
        source = tmp_path / name
        source.write_bytes(name.encode())
        stat = source.stat()
        store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
        assert store.claim_file() == source.resolve()
        from ETL.src.live_monitor.parser import FileBatch

        batch = FileBatch(rows=len(viewers), latest_timestamp=now.timestamp())
        batch.metrics[(minute, "host", "__all__")] = [
            len(viewers), 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        ]
        batch.minute_viewers.update(
            (minute, "host", "__all__", viewer) for viewer in viewers
        )
        store.finish_file(source, batch)

    finish("old.gz", old_minute, ("returning-hash",))
    finish("recent.gz", recent_minute, ("returning-hash", "new-hash"))
    summary = store.snapshot(60)["summaries"]["__all__"]

    assert summary["unique_cliips"] == 2
    assert summary["new_cliips"] == 1
    assert summary["returning_cliips"] == 1
    assert summary["new_cliips"] + summary["returning_cliips"] == summary["unique_cliips"]


def test_restart_requeues_interrupted_file_immediately(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(b"content")
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    assert store.claim_file() == source.resolve()

    assert store.recover(300) == 1
    assert store.claim_file() == source.resolve()


def test_atomic_snapshot_retries_a_transient_windows_share_violation(
    tmp_path: Path, monkeypatch,
) -> None:
    output = tmp_path / "state.json"
    from ETL.src.live_monitor import engine

    real_replace = engine.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporary share violation")
        return real_replace(source, destination)

    monkeypatch.setattr(engine.os, "replace", flaky_replace)
    monkeypatch.setattr(engine.time, "sleep", lambda _seconds: None)
    atomic_write_json(output, {"ok": True})

    assert attempts == 2
    assert json.loads(output.read_text(encoding="utf-8")) == {"ok": True}

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
            assert 'id="visibleRange"' in page
            assert "rolling limit" in page
        with urlopen(f"http://127.0.0.1:{port}/war-room", timeout=2) as response:
            war_room = response.read().decode("utf-8")
            assert "VETO LIVE MONITORING DASHBOARD" in war_room
            assert 'id="audienceChart"' in war_room
            assert 'id="ttfbChart"' in war_room
            assert 'id="timingCoverage"' in war_room
            assert 'id="decodedDeviceBars"' in war_room
            assert 'id="networkBars"' in war_room
            assert 'id="providerQualityRows"' in war_room
            assert 'id="cdnNetworkTypeBars"' in war_room
            assert 'id="deviceCoverage"' in war_room
            assert 'id="asnCoverageMetric"' in war_room
            assert "DECODED DEVICE REQUEST SHARE" in war_room
            assert "function providerQuality(" in war_room
            assert 'id="rangeFrom"' in war_room
            assert 'id="rangeTo"' in war_room
            assert 'id="chartModal"' in war_room
            assert 'id="dataClock"' in war_room
            assert "function completeMinute()" in war_room
            assert 'data-expand="audience"' in war_room
            assert "CDN DELIVERY TIMING" in war_room
            assert "Advertising source not connected" in war_room
        with urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=2) as response:
            assert response.status == 204
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
        "ETL.src.live_monitor.engine.list_recent_relative_key_sets",
        lambda _remote, _hours, local_root=None: (
            ["ak-000001-sample.gz"], ["ak-000001-sample.gz"]
        ),
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


def test_recent_sync_immediately_queues_downloaded_keys(
    tmp_path: Path, monkeypatch,
) -> None:
    config = LiveConfig(spool_root=tmp_path / "spool", state_dir=tmp_path / "state")
    engine = LiveEngine(config)
    key = "ak-000001-current.gz"
    monkeypatch.setattr(
        "ETL.src.live_monitor.engine.list_recent_relative_key_sets",
        lambda _remote, _hours, local_root=None: ([key], [key]),
    )

    def fake_rclone(remote, local, timeout, max_age=None, min_age=None, files_from=None):
        local.mkdir(parents=True, exist_ok=True)
        write_log(local / key, [])
        return True

    engine._rclone = fake_rclone

    assert engine.sync_once()
    assert engine.store.snapshot(10)["files"] == {"pending": 1}


def test_recent_sync_queues_existing_unprocessed_key_without_redownload(
    tmp_path: Path, monkeypatch,
) -> None:
    config = LiveConfig(spool_root=tmp_path / "spool", state_dir=tmp_path / "state")
    engine = LiveEngine(config)
    day = dt.datetime.now(IST)
    local = config.spool_root / engine._day_folder(day)
    local.mkdir(parents=True)
    key = "ak-000001-existing.gz"
    write_log(local / key, [])
    monkeypatch.setattr(
        "ETL.src.live_monitor.engine.list_recent_relative_key_sets",
        lambda _remote, _hours, local_root=None: ([], [key]),
    )
    rclone_calls = []
    engine._rclone = lambda *args, **kwargs: rclone_calls.append((args, kwargs)) or True

    assert engine.sync_once()
    assert not rclone_calls
    assert engine.store.snapshot(10)["files"] == {"pending": 1}


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
