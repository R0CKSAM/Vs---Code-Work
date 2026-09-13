from __future__ import annotations

import importlib.util
import io
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ETL" / "src" / "tools" / "decode_all_distinct_ua_api.py"
SPEC = importlib.util.spec_from_file_location("decode_all_distinct_ua_api", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_configured_keys_are_deduplicated_and_limited_to_four(monkeypatch):
    monkeypatch.setenv("WHATMYUA_KEYS", "key-a,key-b")
    monkeypatch.setenv("WHATMYUA_KEY_1", "key-b")
    monkeypatch.setenv("WHATMYUA_KEY_2", "key-c")
    monkeypatch.setenv("WHATMYUA_KEY_3", "key-d")
    monkeypatch.setenv("WHATMYUA_KEY_4", "key-e")
    args = Namespace(api_keys="", api_key="key-a")

    assert module.configured_api_keys(args) == ["key-a", "key-b", "key-c", "key-d"]


def test_key_pool_rotates_and_persists_daily_quota(tmp_path):
    state_path = tmp_path / "quota.json"
    pool = module.APIKeyPool(["key-a", "key-b"], state_path, daily_limit=2)

    assert pool.next_key() == "key-a"
    pool.record_request("key-a")
    assert pool.next_key() == "key-b"
    pool.record_request("key-b")
    assert pool.next_key() == "key-a"
    pool.record_request("key-a")
    assert pool.next_key() == "key-b"
    pool.record_request("key-b")
    assert pool.next_key() is None

    resumed = module.APIKeyPool(["key-a", "key-b"], state_path, daily_limit=2)
    assert resumed.remaining_capacity() == 0


def test_candidates_prioritize_highest_observed_usage(monkeypatch):
    distinct = pd.DataFrame(
        [
            {"ua_norm": "Low/1.0", "ua_hash": "low"},
            {"ua_norm": "High/1.0", "ua_hash": "high"},
            {"ua_norm": "Middle/1.0", "ua_hash": "middle"},
        ]
    )
    impact = pd.DataFrame(
        [
            {"ua_hash": "low", "rows": 1, "raw_ts_rows": 1, "status_200_ts_rows": 1, "approx_unique_ips": 1},
            {"ua_hash": "high", "rows": 500, "raw_ts_rows": 500, "status_200_ts_rows": 500, "approx_unique_ips": 25},
            {"ua_hash": "middle", "rows": 100, "raw_ts_rows": 100, "status_200_ts_rows": 100, "approx_unique_ips": 10},
        ]
    )
    monkeypatch.setattr(module, "build_impact", lambda _path: impact)
    args = Namespace(include_malformed=False, ua_daily=Path("unused"), api_limit=-1)

    selected = module.select_candidates(distinct, pd.DataFrame(), args)

    assert selected["ua_hash"].tolist() == ["high", "middle", "low"]


def test_candidates_decode_each_normalized_hash_only_once(monkeypatch):
    distinct = pd.DataFrame(
        [
            {"ua_norm": "Duplicate/1.0", "ua_hash": "same"},
            {"ua_norm": "Duplicate%2F1.0", "ua_hash": "same"},
            {"ua_norm": "Other/1.0", "ua_hash": "other"},
        ]
    )
    impact = pd.DataFrame(
        [
            {"ua_hash": "same", "rows": 500, "raw_ts_rows": 500, "status_200_ts_rows": 500, "approx_unique_ips": 20},
            {"ua_hash": "other", "rows": 100, "raw_ts_rows": 100, "status_200_ts_rows": 100, "approx_unique_ips": 5},
        ]
    )
    monkeypatch.setattr(module, "build_impact", lambda _path: impact)
    args = Namespace(include_malformed=False, ua_daily=Path("unused"), api_limit=-1)

    selected = module.select_candidates(distinct, pd.DataFrame(), args)

    assert selected["ua_hash"].tolist() == ["same", "other"]


def test_candidates_honor_requested_decode_status_order(tmp_path, monkeypatch):
    distinct = pd.DataFrame([
        {"ua_norm": "Local/1.0", "ua_hash": "local"},
        {"ua_norm": "Unknown/1.0", "ua_hash": "unknown"},
        {"ua_norm": "-", "ua_hash": "malformed"},
    ])
    lookup = pd.DataFrame([
        {"ua_hash": "local", "decode_status": "decoded_local"},
        {"ua_hash": "unknown", "decode_status": "unknown"},
        {"ua_hash": "malformed", "decode_status": "malformed"},
    ])
    lookup_path = tmp_path / "lookup.parquet"
    lookup.to_parquet(lookup_path, index=False)
    monkeypatch.setattr(module, "build_impact", lambda _path: pd.DataFrame())
    args = Namespace(
        include_malformed=True,
        ua_daily=Path("unused"),
        api_limit=-1,
        priority_statuses="unknown,malformed,decoded_local",
        status_lookup=lookup_path,
    )

    selected = module.select_candidates(distinct, pd.DataFrame(), args)

    assert selected["ua_hash"].tolist() == ["unknown", "malformed", "local"]


def test_log_handles_unicode_outside_windows_code_page(monkeypatch):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    monkeypatch.setattr(module.sys, "stdout", stream)

    module.log("Unicode UA: \u4e2d\u6587")
    stream.flush()

    assert b"\\u4e2d\\u6587" in buffer.getvalue()
