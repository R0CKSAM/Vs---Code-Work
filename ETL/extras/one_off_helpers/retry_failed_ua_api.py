"""Retry only failed WhatMyUserAgent cache rows without touching successes."""

from __future__ import annotations

import importlib.util
import random
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


ETL_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ETL_ROOT / "src" / "tools"
CACHE_PATH = ETL_ROOT / "data" / "cache" / "device_decode" / "whatmyuseragent_all_distinct_ua_cache.parquet"
DISTINCT_UA_PATH = ETL_ROOT / "distinct_UA_Both_All.csv"
OUT_DIR = ETL_ROOT / "output" / "device_decode" / "api_retry"


def load_decoder():
    spec = importlib.util.spec_from_file_location(
        "decode_distinct_ua_lookup", TOOLS_DIR / "decode_distinct_ua_lookup.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("Could not load the shared UA decoder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    decoder = load_decoder()
    cache = decoder.load_api_cache(CACHE_PATH)
    failed = cache.loc[cache["api_status"].fillna("").eq("api_error")].copy()
    if failed.empty:
        print("No failed API cache rows to retry.")
        return

    distinct = decoder.read_distinct_ua_csv(DISTINCT_UA_PATH, None)
    lookup = distinct[["ua_hash", "ua_norm"]].drop_duplicates("ua_hash")
    candidates = failed.merge(lookup, on="ua_hash", how="left")
    candidates = candidates.loc[candidates["ua_norm"].fillna("").str.strip().ne("")].copy()
    if candidates.empty:
        raise SystemExit("Failed cache hashes were not found in the distinct-UA source.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args = SimpleNamespace(
        api_key="NOTREQUIED",
        api_url=decoder.DEFAULT_API_URL,
        api_timeout=20.0,
    )
    results: list[dict[str, str]] = []
    print(f"Retrying {len(candidates)} failed UA API rows only.", flush=True)
    for index, (_, row) in enumerate(candidates.iterrows(), start=1):
        ua_hash = str(row["ua_hash"])
        ua = str(row["ua_norm"])
        print(f"[{index}/{len(candidates)}] {ua_hash[:12]} {ua[:90]}", flush=True)
        try:
            decoded = decoder.api_decode(ua, args)
            status = "decoded_api"
            error = ""
        except Exception as exc:  # API/network errors are persisted for a future retry.
            decoded = decoder.api_error_row(ua_hash, str(exc))
            status = "api_error"
            error = str(exc)

        # Replace this exact failed row; successful cache rows are never rewritten.
        cache = cache.loc[cache["ua_hash"].astype(str).ne(ua_hash)].copy()
        cache = pd.concat([cache, pd.DataFrame([{ "ua_hash": ua_hash, **decoded }])], ignore_index=True)
        decoder.save_api_cache(cache, CACHE_PATH)
        results.append({"ua_hash": ua_hash, "status": status, "error": error, "ua": ua})

        if "rate limit" in error.lower():
            print("API rate limit reached; safely stopping with progress saved.", flush=True)
            break
        if index < len(candidates):
            time.sleep(random.uniform(2.0, 5.0))

    result = pd.DataFrame(results)
    result.to_csv(OUT_DIR / f"failed_ua_retry_{stamp}.csv", index=False, encoding="utf-8-sig")
    print(result["status"].value_counts().to_string(), flush=True)


if __name__ == "__main__":
    main()
