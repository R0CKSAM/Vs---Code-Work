#!/usr/bin/env python3
"""Fill a full WhatMyUserAgent API cache for every distinct valid UA.

This builds the reusable API reference layer. Large log datasets should join
to the final UA lookup by ua_hash instead of calling the API per log row.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ETL_ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent
DECODER_PATH = THIS_DIR / "decode_distinct_ua_lookup.py"
DEFAULT_INPUT = ETL_ROOT / "distinct_UA_Both_All.csv"
DEFAULT_UA_DAILY = ETL_ROOT / "output" / "watch_hours" / "daily_tables" / "user_agents_daily.parquet"
DEFAULT_CACHE = ETL_ROOT / "data" / "cache" / "device_decode" / "whatmyuseragent_all_distinct_ua_cache.parquet"
DEFAULT_OUT_DIR = ETL_ROOT / "output" / "device_decode"
DEFAULT_QUOTA_STATE = ETL_ROOT / "data" / "cache" / "device_decode" / "whatmyuseragent_quota_state.json"
IST = timezone(timedelta(hours=5, minutes=30))


def load_decoder() -> Any:
    spec = importlib.util.spec_from_file_location("decode_distinct_ua_lookup", DECODER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load decoder module from {DECODER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decoder = load_decoder()


def split_api_keys(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\r\n]+", value or "") if item.strip()]


def configured_api_keys(args: argparse.Namespace) -> list[str]:
    """Return at most four unique keys without ever logging their values."""
    candidates: list[str] = []
    candidates.extend(split_api_keys(getattr(args, "api_keys", "")))
    candidates.extend(split_api_keys(os.getenv("WHATMYUA_KEYS", "")))
    for index in range(1, 5):
        candidates.extend(split_api_keys(os.getenv(f"WHATMYUA_KEY_{index}", "")))
    candidates.extend(split_api_keys(getattr(args, "api_key", "")))

    unique: list[str] = []
    for key in candidates:
        if key and key not in unique and key != "NOTREQUIED":
            unique.append(key)
    return unique[:4] or ["NOTREQUIED"]


class APIKeyPool:
    """Daily quota accounting and rotation for provider-authorized API keys."""

    def __init__(self, keys: list[str], state_path: Path, daily_limit: int):
        self.keys = keys
        self.state_path = state_path
        self.daily_limit = max(1, int(daily_limit))
        self.day = datetime.now(IST).date().isoformat()
        self.position = 0
        self.state = self._load()

    @staticmethod
    def fingerprint(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _load(self) -> dict[str, Any]:
        default = {"ist_date": self.day, "keys": {}}
        if not self.state_path.exists():
            return default
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return default
        if not isinstance(loaded, dict) or loaded.get("ist_date") != self.day:
            return default
        if not isinstance(loaded.get("keys"), dict):
            loaded["keys"] = {}
        return loaded

    def _entry(self, key: str) -> dict[str, Any]:
        fingerprint = self.fingerprint(key)
        entry = self.state["keys"].setdefault(
            fingerprint, {"requests_attempted": 0, "unavailable_reason": ""}
        )
        if "requests_attempted" not in entry:
            entry["requests_attempted"] = int(entry.pop("successful_requests", 0))
        return entry

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def is_available(self, key: str) -> bool:
        entry = self._entry(key)
        return (
            not entry.get("unavailable_reason")
            and int(entry.get("requests_attempted", 0)) < self.daily_limit
        )

    def next_key(self) -> str | None:
        for offset in range(len(self.keys)):
            index = (self.position + offset) % len(self.keys)
            key = self.keys[index]
            if self.is_available(key):
                self.position = (index + 1) % len(self.keys)
                return key
        return None

    def record_request(self, key: str) -> None:
        entry = self._entry(key)
        entry["requests_attempted"] = int(entry.get("requests_attempted", 0)) + 1
        if entry["requests_attempted"] >= self.daily_limit:
            entry["unavailable_reason"] = "local_daily_limit"
        self.save()

    def mark_unavailable(self, key: str, reason: str) -> None:
        self._entry(key)["unavailable_reason"] = reason
        self.save()

    def remaining_capacity(self) -> int:
        return sum(
            max(0, self.daily_limit - int(self._entry(key).get("requests_attempted", 0)))
            for key in self.keys if not self._entry(key).get("unavailable_reason")
        )

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "key_id": self.fingerprint(key),
                "requests_attempted": int(self._entry(key).get("requests_attempted", 0)),
                "remaining": max(
                    0, self.daily_limit - int(self._entry(key).get("requests_attempted", 0))
                ),
                "unavailable_reason": self._entry(key).get("unavailable_reason", ""),
            }
            for key in self.keys
        ]


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def build_impact(ua_daily_path: Path) -> pd.DataFrame:
    if not ua_daily_path.exists():
        return pd.DataFrame(columns=["ua_hash", "rows", "raw_ts_rows", "status_200_ts_rows", "approx_unique_ips"])
    daily = pd.read_parquet(ua_daily_path)
    if daily.empty or "userAgent" not in daily.columns:
        return pd.DataFrame(columns=["ua_hash", "rows", "raw_ts_rows", "status_200_ts_rows", "approx_unique_ips"])
    daily = daily.copy()
    daily["ua_hash"] = daily["userAgent"].map(decoder.normalize_ua).map(decoder.ua_hash)
    for col in ["rows", "raw_ts_rows", "status_200_ts_rows", "approx_unique_ips"]:
        if col not in daily.columns:
            daily[col] = 0
        daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0)
    return (
        daily.groupby("ua_hash", dropna=False)[["rows", "raw_ts_rows", "status_200_ts_rows", "approx_unique_ips"]]
        .sum()
        .reset_index()
    )


def load_cache(path: Path) -> pd.DataFrame:
    return decoder.load_api_cache(path)


def save_cache(cache: pd.DataFrame, path: Path) -> None:
    decoder.save_api_cache(cache, path)


def select_candidates(distinct: pd.DataFrame, combined_cache: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    candidates = distinct.copy()
    candidates["malformed_reason"] = candidates["ua_norm"].map(decoder.malformed_reason)
    if not args.include_malformed:
        candidates = candidates[candidates["malformed_reason"].eq("")].copy()

    # Only a successful API response satisfies full-fill coverage. A prior
    # timeout/rate-limit row is retryable and must not permanently suppress it.
    successful = set(
        combined_cache.loc[
            combined_cache["api_status"].astype(str).eq("decoded_api"), "ua_hash"
        ].astype(str)
    ) if not combined_cache.empty else set()
    candidates = candidates[~candidates["ua_hash"].astype(str).isin(successful)].copy()

    impact = build_impact(args.ua_daily)
    if not impact.empty:
        candidates = candidates.merge(impact, on="ua_hash", how="left")
    for col in ["rows", "raw_ts_rows", "status_200_ts_rows", "approx_unique_ips"]:
        if col not in candidates.columns:
            candidates[col] = 0
        candidates[col] = pd.to_numeric(candidates[col], errors="coerce").fillna(0)

    # Spend scarce API quota on the UAs that affect the most real requests.
    candidates = candidates.sort_values(
        ["raw_ts_rows", "approx_unique_ips", "rows", "ua_norm"],
        ascending=[False, False, False, True],
    )
    if args.api_limit > 0:
        candidates = candidates.head(args.api_limit)
    return candidates


def run_api(
    candidates: pd.DataFrame,
    own_cache: pd.DataFrame,
    args: argparse.Namespace,
    key_pool: APIKeyPool,
) -> pd.DataFrame:
    if args.api_limit == 0 or candidates.empty:
        return own_cache
    rows: list[dict[str, Any]] = []
    last_request_at: float | None = None
    for idx, (_, row) in enumerate(candidates.iterrows(), start=1):
        ua = decoder.safe_text(row["ua_norm"])
        ua_hash = decoder.safe_text(row["ua_hash"])
        log(f"API full-fill {idx}/{len(candidates)} ua_hash={ua_hash[:12]} ua={ua[:100]}")
        candidate_completed = False
        while True:
            api_key = key_pool.next_key()
            if api_key is None:
                log("All configured API keys reached their daily limit or became unavailable.")
                break
            if last_request_at is not None:
                target_delay = random.uniform(
                    args.api_sleep_min_seconds, args.api_sleep_max_seconds
                )
                time.sleep(max(0.0, target_delay - (time.monotonic() - last_request_at)))
            args.api_key = api_key
            key_id = key_pool.fingerprint(api_key)
            key_pool.record_request(api_key)
            try:
                last_request_at = time.monotonic()
                decoded = decoder.api_decode(ua, args)
                rows.append({"ua_hash": ua_hash, **decoded})
                candidate_completed = True
                break
            except Exception as exc:
                last_request_at = time.monotonic()
                error = str(exc)
                log(f"API error on key {key_id}: {error}")
                if decoder.is_auth_error(error):
                    key_pool.mark_unavailable(api_key, "authentication_error")
                    continue
                if decoder.is_rate_limit_error(error):
                    key_pool.mark_unavailable(api_key, "provider_rate_limit")
                    if args.stop_on_rate_limit:
                        continue
                rows.append(decoder.api_error_row(ua_hash, error))
                candidate_completed = True
                break

        if not candidate_completed:
            break

        if args.api_flush_every > 0 and len(rows) >= args.api_flush_every:
            own_cache = pd.concat([own_cache, pd.DataFrame(rows)], ignore_index=True)
            save_cache(own_cache, args.api_cache)
            rows = []

    if rows:
        own_cache = pd.concat([own_cache, pd.DataFrame(rows)], ignore_index=True)
        save_cache(own_cache, args.api_cache)
    return load_cache(args.api_cache)


def write_manifest(args: argparse.Namespace, distinct: pd.DataFrame, valid_count: int, combined_before: pd.DataFrame, own_after: pd.DataFrame, selected_count: int, started: float, key_pool: APIKeyPool) -> None:
    combined_after = decoder.combine_api_caches(
        load_cache(decoder.DEFAULT_CACHE),
        load_cache(decoder.DEFAULT_LOCAL_VERIFIED_CROSSCHECK_CACHE),
        own_after,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input),
        "api_url": args.api_url,
        "api_cache": str(args.api_cache),
        "quota_state": str(args.api_quota_state),
        "key_count": len(key_pool.keys),
        "key_usage": key_pool.summary(),
        "stats": {
            "distinct_ua_rows": int(len(distinct)),
            "valid_distinct_ua_rows": int(valid_count),
            "combined_api_cached_before": int(len(combined_before)),
            "new_candidates_this_run": int(selected_count),
            "own_full_cache_rows": int(len(own_after)),
            "combined_api_cached_after": int(len(combined_after)),
            "remaining_valid_after": int(max(valid_count - len(combined_after), 0)),
            "elapsed_seconds": round(time.time() - started, 2),
        },
    }
    path = args.out_dir / "ua_api_all_distinct_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Manifest written: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API-decode every distinct valid UA into a reusable cache.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--column", default=None)
    parser.add_argument("--ua-daily", type=Path, default=DEFAULT_UA_DAILY)
    parser.add_argument("--api-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--api-limit", type=int, default=100, help="0 status/manifest only; positive checks N new UAs; -1 checks all remaining valid UAs.")
    parser.add_argument("--api-key", default=os.getenv("WHATMYUA_KEY", "NOTREQUIED"))
    parser.add_argument("--api-keys", default="", help="Comma-separated keys; prefer WHATMYUA_KEYS or WHATMYUA_KEY_1..4 in .env.")
    parser.add_argument("--api-daily-limit-per-key", type=int, default=1000)
    parser.add_argument("--api-quota-state", type=Path, default=DEFAULT_QUOTA_STATE)
    parser.add_argument("--api-url", default=decoder.DEFAULT_API_URL)
    parser.add_argument("--api-timeout", type=float, default=20.0)
    parser.add_argument("--api-sleep-min-seconds", type=float, default=4.0)
    parser.add_argument("--api-sleep-max-seconds", type=float, default=5.0)
    parser.add_argument("--api-flush-every", type=int, default=5)
    parser.add_argument("--stop-on-rate-limit", action="store_true", default=True)
    parser.add_argument("--include-malformed", action="store_true")
    return parser.parse_args()


def main() -> None:
    decoder.load_env_file()
    args = parse_args()
    args.input = args.input.expanduser().resolve()
    args.ua_daily = args.ua_daily.expanduser().resolve()
    args.api_cache = args.api_cache.expanduser().resolve()
    args.api_quota_state = args.api_quota_state.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    if args.api_sleep_min_seconds < 3.0:
        raise ValueError("WhatMyUserAgent requires at least 3 seconds per IP; use 4 seconds or more.")
    if args.api_sleep_max_seconds < args.api_sleep_min_seconds:
        raise ValueError("--api-sleep-max-seconds must be >= --api-sleep-min-seconds")

    keys = configured_api_keys(args)
    key_pool = APIKeyPool(keys, args.api_quota_state, args.api_daily_limit_per_key)

    started = time.time()
    distinct = decoder.read_distinct_ua_csv(args.input, args.column)
    valid_count = int(distinct["ua_norm"].map(decoder.malformed_reason).eq("").sum())
    own_cache = load_cache(args.api_cache)
    combined_before = decoder.combine_api_caches(
        load_cache(decoder.DEFAULT_CACHE),
        load_cache(decoder.DEFAULT_LOCAL_VERIFIED_CROSSCHECK_CACHE),
        own_cache,
    )
    candidates = select_candidates(distinct, combined_before, args)
    capacity = key_pool.remaining_capacity()
    if args.api_limit == 0:
        candidates = candidates.head(0)
    else:
        candidates = candidates.head(capacity)
    log(
        f"Distinct UA rows: {len(distinct):,}; valid: {valid_count:,}; "
        f"combined API cached: {len(combined_before):,}; keys: {len(keys)}; "
        f"tracked quota remaining today: {capacity:,}; selected this run: {len(candidates):,}"
    )
    own_after = run_api(candidates, own_cache, args, key_pool)
    write_manifest(
        args, distinct, valid_count, combined_before, own_after,
        len(candidates), started, key_pool,
    )


if __name__ == "__main__":
    main()
