#!/usr/bin/env python3
"""Rebuild Overview device CSVs directly from a backup lake source.

This mirrors the strict Z-source Overview rebuild style: scan one resolved
source/date partition at a time, write checkpoint parts, merge them into the
Overview-compatible device_daily.csv and device_snapshot.csv, then validate the
daily device counts against source/date aggregates.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ETL.src.common import lake_partitions
from ETL.src.tools.repair_overview_true_source import reader_sql

IST_OFFSET_SECONDS = 19_800
DAILY_COLUMNS = [
    "source",
    "device_id",
    "utc_date",
    "rows_on_date",
    "distinct_ip",
    "distinct_ip_ua",
    "distinct_sessions",
]
SNAPSHOT_COLUMNS = [
    "device_id",
    "first_seen_utc_date",
    "last_seen_utc_date",
    "days_seen",
    "total_rows",
    "distinct_ip_day_sum",
    "distinct_ip_ua_day_sum",
    "distinct_sessions_day_sum",
]


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Overview device CSVs from backup lake parquet.")
    parser.add_argument("--lake-root", default=r"Z:\Veto Logs Backup\DO NOT DELETE")
    parser.add_argument("--out-dir", default=str(Path("ETL") / "output" / "overview_z_source_rebuild"))
    parser.add_argument("--sources", default="stream,fast")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="8GB")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def qs_extract(qs_col: str, param: str) -> str:
    extracted = (
        f"NULLIF(regexp_extract(COALESCE({qs_col}, ''), "
        f"'(?:^|[?&]){param}=([^&]*)', 1), '')"
    )
    # Literal placeholders are not real identities. Keep this aligned with
    # repair_overview_true_source.py so device_daily reconciles with Overview.
    return f"CASE WHEN lower(trim({extracted})) IN ('null', 'nan', 'none', 'na') THEN NULL ELSE {extracted} END"


def ist_date_sql(epoch_expr: str) -> str:
    return (
        "CAST(epoch_ms(CAST(FLOOR(("
        f"TRY_CAST({epoch_expr} AS DOUBLE) + {IST_OFFSET_SECONDS}"
        ") * 1000) AS BIGINT)) AS DATE)"
    )


def partition_row_count(partition) -> int:
    total = 0
    for file in partition.files:
        total += int(pq.read_metadata(file).num_rows or 0)
    return total


def partition_metadata(partitions: list) -> pd.DataFrame:
    rows = []
    for partition in partitions:
        rows.append(
            {
                "source": partition.source,
                "date": partition.date_text,
                "files": len(partition.files),
                "rows_true": partition_row_count(partition),
                "day_dir": str(partition.day_dir),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["source", "date", "files", "rows_true", "day_dir"])
    return pd.DataFrame(rows).sort_values(["date", "source"])


def part_path(parts_dir: Path, date_key: str) -> Path:
    return parts_dir / f"{date_key}_device_daily.csv"


def is_checkpoint_valid(parts_dir: Path, date_key: str) -> bool:
    path = part_path(parts_dir, date_key)
    if not path.exists():
        return False
    try:
        pd.read_csv(path, nrows=5)
    except Exception:
        return False
    return True


def write_empty_daily(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(DAILY_COLUMNS) + "\n", encoding="utf-8")


def process_date(date_key: str, partitions: list, parts_dir: Path, args: argparse.Namespace) -> None:
    out_path = part_path(parts_dir, date_key)
    reader = reader_sql(partitions, lake_partitions)
    device_id = qs_extract("queryStr", "device_id")
    session_id = qs_extract("queryStr", "session_id")
    # The Z-source Overview rebuild is source-partition based. Device daily
    # must use the same date basis so dist_dev reconciles exactly with Overview.
    partition_date = "make_date(CAST(year AS INT), CAST(month AS INT), CAST(day AS INT))"

    con = duckdb.connect()
    con.execute(f"SET threads={max(1, int(args.threads))}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET preserve_insertion_order=false")
    try:
        con.execute(
            f"""
            COPY (
                WITH base AS (
                    SELECT
                        LOWER(COALESCE(NULLIF(CAST(source AS VARCHAR), ''), 'stream')) AS source,
                        {device_id} AS device_id,
                        {partition_date} AS utc_date,
                        cliIP,
                        UA,
                        {session_id} AS session_id
                    FROM {reader}
                    WHERE queryStr IS NOT NULL
                      AND queryStr LIKE '%device_id=%'
                      AND {device_id} IS NOT NULL
                )
                SELECT
                    source,
                    device_id,
                    utc_date,
                    COUNT(*) AS rows_on_date,
                    COUNT(DISTINCT cliIP) AS distinct_ip,
                    COUNT(DISTINCT (cliIP, UA)) AS distinct_ip_ua,
                    COUNT(DISTINCT session_id) AS distinct_sessions
                FROM base
                GROUP BY source, device_id, utc_date
                ORDER BY utc_date DESC, source, rows_on_date DESC
            ) TO '{sql_path(out_path)}' (HEADER, DELIMITER ',');
            """
        )
    finally:
        con.close()

    if not out_path.exists():
        write_empty_daily(out_path)


def merge_daily(parts_dir: Path, out_dir: Path, truth: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for date_key in sorted(truth["date"].unique()):
        path = part_path(parts_dir, date_key)
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        frames.append(df)

    if frames:
        daily = pd.concat(frames, ignore_index=True)
        for col in DAILY_COLUMNS:
            if col not in daily.columns:
                daily[col] = "" if col in {"source", "device_id", "utc_date"} else 0
        daily = daily[DAILY_COLUMNS]
        daily["source"] = daily["source"].astype(str).str.lower().str.strip().replace("", "stream")
        daily["device_id"] = daily["device_id"].astype(str).str.strip()
        daily["utc_date"] = daily["utc_date"].astype(str).str[:10]
        for col in ["rows_on_date", "distinct_ip", "distinct_ip_ua", "distinct_sessions"]:
            daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0).astype("int64")
        daily = daily[
            daily["device_id"].ne("")
            & daily["device_id"].str.lower().ne("nan")
            & daily["utc_date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
        ]
        daily = daily.sort_values(["utc_date", "source", "rows_on_date"], ascending=[False, True, False])
    else:
        daily = pd.DataFrame(columns=DAILY_COLUMNS)

    daily_path = out_dir / "device_daily.csv"
    daily.to_csv(daily_path, index=False)
    return daily


def build_snapshot(daily: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    if daily.empty:
        snapshot = pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    else:
        snapshot = (
            daily.groupby("device_id", as_index=False)
            .agg(
                first_seen_utc_date=("utc_date", "min"),
                last_seen_utc_date=("utc_date", "max"),
                days_seen=("utc_date", "nunique"),
                total_rows=("rows_on_date", "sum"),
                distinct_ip_day_sum=("distinct_ip", "sum"),
                distinct_ip_ua_day_sum=("distinct_ip_ua", "sum"),
                distinct_sessions_day_sum=("distinct_sessions", "sum"),
            )
            .sort_values(["last_seen_utc_date", "total_rows"], ascending=[False, False])
        )
        snapshot = snapshot[SNAPSHOT_COLUMNS]

    snapshot.to_csv(out_dir / "device_snapshot.csv", index=False)
    return snapshot


def write_validation(out_dir: Path, truth: pd.DataFrame, daily: pd.DataFrame, snapshot: pd.DataFrame) -> dict:
    if daily.empty:
        daily_counts = pd.DataFrame(columns=["source", "date", "device_rows", "distinct_devices", "rows_on_date"])
    else:
        daily_counts = (
            daily.groupby(["source", "utc_date"], as_index=False)
            .agg(
                device_rows=("device_id", "count"),
                distinct_devices=("device_id", "nunique"),
                rows_on_date=("rows_on_date", "sum"),
            )
            .rename(columns={"utc_date": "date"})
        )

    truth_keys = truth[["source", "date", "rows_true"]].copy()
    validation = truth_keys.merge(daily_counts, on=["source", "date"], how="left")
    for col in ["device_rows", "distinct_devices", "rows_on_date"]:
        validation[col] = pd.to_numeric(validation[col], errors="coerce").fillna(0).astype("int64")
    validation.to_csv(out_dir / "z_source_device_validation.csv", index=False)

    manifest = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source_rows": int(len(truth)),
        "daily_rows": int(len(daily)),
        "snapshot_rows": int(len(snapshot)),
        "total_device_request_rows": int(daily["rows_on_date"].sum()) if not daily.empty else 0,
        "sources": {
            source: {
                "source_dates": int(group["date"].nunique()),
                "source_rows": int(group["rows_true"].sum()),
                "device_dates": int((daily[daily["source"] == source]["utc_date"].nunique()) if not daily.empty else 0),
                "device_daily_rows": int((daily["source"] == source).sum()) if not daily.empty else 0,
            }
            for source, group in truth.groupby("source")
        },
        "date_min": str(truth["date"].min()) if not truth.empty else "",
        "date_max": str(truth["date"].max()) if not truth.empty else "",
    }
    (out_dir / "z_source_device_summary.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    args = parse_args()
    lake_root = Path(args.lake_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    parts_dir = out_dir / "device_parts"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    if not lake_root.exists():
        raise SystemExit(f"Backup lake root not found: {lake_root}")

    sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    log(f"Discovering backup lake partitions: {lake_root}")
    partitions = lake_partitions.discover_partitions(
        [lake_root],
        sources=sources,
        start=args.start,
        end=args.end,
    )
    if not partitions:
        raise SystemExit("No partitions found.")

    truth = partition_metadata(partitions)
    truth.to_csv(out_dir / "z_source_device_truth_metadata.csv", index=False)
    dates = sorted(truth["date"].unique())
    log(
        f"Found {len(dates)} day(s), {len(partitions)} source/date partition(s), "
        f"{int(truth['rows_true'].sum()):,} source rows"
    )

    started = datetime.now()
    done = 0
    skipped = 0
    failed = []
    for idx, date_key in enumerate(dates, start=1):
        day_truth = truth[truth["date"] == date_key]
        day_partitions = [partition for partition in partitions if partition.date_text == date_key]
        expected_rows = int(day_truth["rows_true"].sum())
        if not args.force and is_checkpoint_valid(parts_dir, date_key):
            skipped += 1
            log(f"[skip] {idx}/{len(dates)} {date_key} rows={expected_rows:,} checkpoint valid")
            continue
        log(f"[run ] {idx}/{len(dates)} {date_key} rows={expected_rows:,} sources={','.join(sorted(day_truth['source'].unique()))}")
        try:
            process_date(date_key, day_partitions, parts_dir, args)
            done += 1
            elapsed = datetime.now() - started
            log(f"[done] {idx}/{len(dates)} {date_key} elapsed={str(elapsed).split('.')[0]}")
        except Exception as exc:
            failed.append({"date": date_key, "error": str(exc)})
            log(f"[fail] {idx}/{len(dates)} {date_key}: {exc}")

    if failed:
        pd.DataFrame(failed).to_csv(out_dir / "z_source_device_failures.csv", index=False)
        raise SystemExit(f"Failed dates: {len(failed)}. See z_source_device_failures.csv")

    log("Merging device_daily.csv")
    daily = merge_daily(parts_dir, out_dir, truth)
    log("Building device_snapshot.csv")
    snapshot = build_snapshot(daily, out_dir)
    summary = write_validation(out_dir, truth, daily, snapshot)
    summary.update({"processed_dates": done, "skipped_dates": skipped, "lake_root": str(lake_root)})
    (out_dir / "z_source_device_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log("Summary: " + json.dumps(summary))
    log(f"Device daily written   : {out_dir / 'device_daily.csv'}")
    log(f"Device snapshot written: {out_dir / 'device_snapshot.csv'}")


if __name__ == "__main__":
    main()

