from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ETL" / "src" / "tools" / "decode_all_distinct_ua_api.py"
SPEC = importlib.util.spec_from_file_location("decode_all_distinct_ua_api", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_configured_keys_are_deduplicated_and_limited_to_three(monkeypatch):
    monkeypatch.setenv("WHATMYUA_KEYS", "key-a,key-b")
    monkeypatch.setenv("WHATMYUA_KEY_1", "key-b")
    monkeypatch.setenv("WHATMYUA_KEY_2", "key-c")
    monkeypatch.setenv("WHATMYUA_KEY_3", "key-d")
    args = Namespace(api_keys="", api_key="key-a")

    assert module.configured_api_keys(args) == ["key-a", "key-b", "key-c"]


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
