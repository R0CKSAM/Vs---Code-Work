from __future__ import annotations

import datetime as dt
import gzip
import json

import pytest

from ETL.src.live_monitor.parser import (
    CHANNEL_MAPPING_VERSION,
    IST,
    delivery_channel,
    matching_targets,
    parse_gzip_file,
)
from ETL.src.live_monitor.store import LiveStore


@pytest.mark.parametrize("path,expected", [
    ("hls/live/2111218/YrfMusic/1.m3u8", "YRF Music"),
    ("/HLS/live/2111218/YrfMusic/segment.ts?token=test", "YRF Music"),
    ("https://yrf-veto.akamaized.net/hls/live/2111218/YrfMusic/1.m3u8", "YRF Music"),
    ("https://[invalid/YrfMusic/1.m3u8", "Other"),
    ("hls/live/2111218/SagaMusic/1.m3u8", "SAGA Music"),
    ("hls/live/2111218/SagaHaryanvi/1.m3u8", "Saga Music Haryanvi"),
    ("hls/live/2111218/SikhRatnavali/1.m3u8", "Sikh Ratnavali"),
    ("YrfMusic/master.m3u8", "YRF Music"),
    ("hls/live/2111218/unknown/1.m3u8", "Other"),
    ("hls/live/2111218/YrfMusicExtra/1.m3u8", "Other"),
    ("hls/live/2111218/1.m3u8?channel=YrfMusic", "Other"),
])
def test_yrf_legacy_paths_require_a_recognized_channel(path, expected):
    assert delivery_channel("YRF-VETO.AKAMAIZED.NET:443", path) == expected


@pytest.mark.parametrize("host,path,expected", [
    ("epic-kid-veto.akamaized-staging.net", "epic-kids-o_360p/chunks.m3u8", "Epic Kids (staging)"),
    ("epic-veto.akamaized-staging.net", "epic-bhojpuri-o_360p/chunks.m3u8", "Epic Bhojpuri (staging)"),
    ("epic-music-veto.akamaized-staging.net:443", "epic-music-o_360p/chunks.m3u8", "Epic Music (staging)"),
    ("epic-bharat-veto.akamaized-staging.net", "master_360.m3u8", "Epic Bharat (staging)"),
    ("epic-bharat-veto.akamaized-staging.net", "/epic_bharat/master.m3u8", "Epic Bharat (staging)"),
    ("epic-kid-veto.akamaized.net", "epic_kids/playlist.m3u8", "Epic Kids"),
    ("epic-music-veto.akamaized.net", "epic-music-o_720p/segment.ts", "Epic Music"),
    ("epic-tv-veto.akamaized.net", "epic_tv/master.m3u8", "Epic TV"),
    ("epic-veto.akamaized.net", "epic_bhojpuri/playlist.m3u8", "Epic Bhojpuri"),
    ("epic-kid-veto.akamaized-staging.net", "unknown/chunks.m3u8", "Other"),
    ("epic-kid-veto.akamaized-staging.net", "epic_bhojpuri/playlist.m3u8", "Other"),
    ("epic-bharat-veto.akamaized-staging.net", "unknown/master_360.m3u8", "Other"),
    ("epic-kid-veto.akamaized-staging.net", "master_360.m3u8", "Other"),
    ("other.example", "epic-kids-o_360p/chunks.m3u8", "Other"),
    ("yrf-veto.akamaized.net.example", "hls/live/2111218/YrfMusic/1.m3u8", "Other"),
])
def test_epic_staging_is_explicit_and_cannot_leak_to_production(host, path, expected):
    assert delivery_channel(host, path) == expected


def test_davis_and_ordinary_channels_are_unchanged():
    now = dt.datetime(2026, 9, 19, 12, tzinfo=IST)
    assert matching_targets(now, "daviscup-veto.akamaized.net",
                            "f98c8ae68a354ab59a4e28e3dd700d4f/playlist.m3u8") == ("__all__", "f98c8")
    assert delivery_channel("veto.akamaized.net", "v1/vglive-sk-274906/chunk.ts") == "India TV"
    assert CHANNEL_MAPPING_VERSION == 4  # No destructive historical rebuild.


def test_failed_requests_are_relabelled_but_not_deleted_or_added_to_watch_time(tmp_path):
    source = tmp_path / "delivery.gz"
    now = dt.datetime.now(IST).replace(second=0, microsecond=0)
    records = [
        ("yrf-veto.akamaized.net", "hls/live/2111218/YrfMusic/1.m3u8", 404),
        ("epic-kid-veto.akamaized-staging.net", "epic-kids-o_360p/chunks.m3u8", 404),
        ("epic-music-veto.akamaized-staging.net", "epic-music-o_360p/chunks.m3u8", 503),
        ("yrf-veto.akamaized.net", "YrfMusic/segment.ts", 200),
    ]
    with gzip.open(source, "wt", encoding="utf-8") as output:
        for host, path, status in records:
            output.write(json.dumps({
                "reqTimeSec": now.timestamp(), "reqHost": host, "reqPath": path,
                "statusCode": status, "bytes": 100, "cliIP": "192.0.2.1",
            }) + "\n")
    batch = parse_gzip_file(source, ())
    assert batch.rows == 4
    assert all(target != "Other" for _, _, target in batch.metrics)
    store = LiveStore(tmp_path / "state.sqlite3")
    stat = source.stat()
    store.observe_file(source, stat.st_size, stat.st_mtime_ns, 1)
    assert store.claim_file() == source.resolve()
    store.finish_file(source, batch)
    snapshot = store.snapshot(60)
    summaries = snapshot["summaries"]
    assert summaries["__all__"]["requests"] == 4
    assert summaries["__all__"]["bytes"] == 400
    assert summaries["__all__"]["errors_4xx"] == 2
    assert summaries["__all__"]["errors_5xx"] == 1
    assert summaries["__all__"]["estimated_watch_seconds"] == 6
    assert summaries["__all__"]["unique_cliips"] == 1
    assert summaries["YRF Music"]["requests"] == 2
    assert summaries["Epic Kids (staging)"]["estimated_watch_seconds"] == 0
    assert summaries["Epic Music (staging)"]["errors_5xx"] == 1
    assert store.claim_file() is None
