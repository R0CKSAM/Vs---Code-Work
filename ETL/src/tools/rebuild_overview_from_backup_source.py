#!/usr/bin/env python3
"""Rebuild Overview files from one backup lake source, without reusing marts.

The normal Overview path can use compact marts for speed. This tool is stricter:
it scans the requested backup lake directly, writes per-day checkpoints, then
builds overview_report.xlsx and overview_source_daily.csv from those checkpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
from ETL.src.overview import overViewGenerator as ov
from ETL.src.tools.repair_overview_true_source import (
    exact_query,
    overview_rows_from_df,
    reader_sql,
    source_rows_from_df,
)


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strictly rebuild Overview from backup lake parquet source.")
    parser.add_argument("--lake-root", default=r"Z:\Veto Logs Backup\DO NOT DELETE")
    parser.add_argument("--out-dir", default=str(Path("ETL") / "output" / "overview_z_source_rebuild"))
    parser.add_argument("--sources", default="stream,fast")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="8GB")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-html", action="store_true")
    return parser.parse_args()


def partition_metadata(partitions: list) -> pd.DataFrame:
    rows = []
    for partition in partitions:
        row_count = 0
        byte_count = 0
        for file in partition.files:
            row_count += int(pq.read_metadata(file).num_rows or 0)
            byte_count += int(file.stat().st_size)
        rows.append(
            {
                "source": partition.source,
                "date": partition.date_text,
                "files": len(partition.files),
                "rows_true": row_count,
                "bytes_on_disk": byte_count,
                "day_dir": str(partition.day_dir),
            }
        )
    return pd.DataFrame(rows).sort_values(["date", "source"])


def date_part_path(parts_dir: Path, date_key: str, kind: str) -> Path:
    return parts_dir / f"{date_key}_{kind}.csv"


def is_checkpoint_valid(parts_dir: Path, date_key: str, expected_rows: int) -> bool:
    source_path = date_part_path(parts_dir, date_key, "source")
    date_path = date_part_path(parts_dir, date_key, "date")
    if not source_path.exists() or not date_path.exists():
        return False
    try:
        source_rows = pd.read_csv(source_path)
        date_rows = pd.read_csv(date_path)
    except Exception:
        return False
    if source_rows.empty or date_rows.empty:
        return False
    return int(pd.to_numeric(source_rows["total_rows"], errors="coerce").fillna(0).sum()) == int(expected_rows)


def process_date(date_key: str, partitions: list, parts_dir: Path, args: argparse.Namespace) -> None:
    reader = reader_sql(partitions, lake_partitions)
    con = duckdb.connect()
    con.execute(f"SET threads={max(1, int(args.threads))}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET preserve_insertion_order=false")
    try:
        source_df = exact_query(con, reader, group_source=True)
        date_df = exact_query(con, reader, group_source=False)
    finally:
        con.close()
    source_df.to_csv(date_part_path(parts_dir, date_key, "source"), index=False)
    date_df.to_csv(date_part_path(parts_dir, date_key, "date"), index=False)


def merge_outputs(out_dir: Path, parts_dir: Path, truth: pd.DataFrame, lake_root: Path) -> dict:
    source_frames = []
    date_frames = []
    for date_key in sorted(truth["date"].unique()):
        source_path = date_part_path(parts_dir, date_key, "source")
        date_path = date_part_path(parts_dir, date_key, "date")
        if source_path.exists():
            source_frames.append(pd.read_csv(source_path))
        if date_path.exists():
            date_frames.append(pd.read_csv(date_path))
    if not source_frames or not date_frames:
        raise RuntimeError("No checkpoint parts found to merge.")

    source_df = pd.concat(source_frames, ignore_index=True)
    date_df = pd.concat(date_frames, ignore_index=True)
    source_rows = source_rows_from_df(source_df)
    overview_rows = overview_rows_from_df(date_df)
    source_rows.sort(key=lambda row: (str(row.get("date", "")), str(row.get("source", ""))))
    overview_rows.sort(key=lambda row: datetime.strptime(row["ist_date"], "%d/%m/%y"))

    ov.write_source_rows_csv(out_dir / ov.SOURCE_DAILY_FILENAME, source_rows)
    date_range_ist, time_range_ist = ov.mart_date_ranges(overview_rows)
    ov.write_overview_excel(
        output_path=out_dir / ov.OVERVIEW_FILENAME,
        data_rows=overview_rows,
        lake_root=lake_root,
        year_filter=None,
        month_filter=None,
        total_rows_pa=int(truth["rows_true"].sum()),
        total_files=int(truth["files"].sum()),
        date_range_ist=date_range_ist,
        time_range_ist=time_range_ist,
    )

    output_source = pd.DataFrame(source_rows)
    output_source["source"] = output_source["source"].astype(str).str.lower()
    output_source["date"] = output_source["date"].astype(str).str[:10]
    output_source["rows"] = pd.to_numeric(output_source["rows"], errors="coerce").fillna(0).astype("int64")
    check = truth.merge(
        output_source[["source", "date", "rows"]],
        on=["source", "date"],
        how="outer",
    )
    check["rows_true"] = check["rows_true"].fillna(0).astype("int64")
    check["rows"] = check["rows"].fillna(0).astype("int64")
    check["diff"] = check["rows"] - check["rows_true"]
    check.to_csv(out_dir / "z_source_rebuild_validation.csv", index=False)

    return {
        "source_rows": len(source_rows),
        "overview_rows": len(overview_rows),
        "source_mismatches": int((check["diff"] != 0).sum()),
        "combined_rows": int(truth["rows_true"].sum()),
        "combined_days": int(truth["date"].nunique()),
        "start": str(truth["date"].min()),
        "end": str(truth["date"].max()),
    }


def generate_html(out_dir: Path, lake_root: Path) -> None:
    env = os.environ.copy()
    env["VG_ETL_LAKE_ROOT"] = str(lake_root)
    env["VG_OVERVIEW_IDENTITY_DEVICE_DAILY"] = str(out_dir / "__no_identity_mart__.parquet")
    cmd = [
        sys.executable,
        str(Path("ETL") / "src" / "dashboards" / "overViewDashboard" / "generate_dashboard.py"),
        "--data-dir",
        str(out_dir),
    ]
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    args = parse_args()
    lake_root = Path(args.lake_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    parts_dir = out_dir / "parts"
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
    truth.to_csv(out_dir / "z_source_rebuild_truth_metadata.csv", index=False)
    by_date = truth.groupby("date", as_index=False).agg(rows_true=("rows_true", "sum"), files=("files", "sum"))
    by_date.to_csv(out_dir / "z_source_rebuild_truth_by_date.csv", index=False)

    log(
        "Found "
        f"{truth['date'].nunique()} day(s), {len(partitions)} source/date partition(s), "
        f"{int(truth['rows_true'].sum()):,} rows"
    )

    grouped = {date_key: list(items.index) for date_key, items in truth.groupby("date")}
    dates = sorted(grouped)
    done = 0
    skipped = 0
    failed: list[dict] = []
    start_time = datetime.now()

    for idx, date_key in enumerate(dates, start=1):
        day_truth = truth[truth["date"] == date_key]
        expected_rows = int(day_truth["rows_true"].sum())
        day_partitions = [partition for partition in partitions if partition.date_text == date_key]
        if not args.force and is_checkpoint_valid(parts_dir, date_key, expected_rows):
            skipped += 1
            log(f"[skip] {idx}/{len(dates)} {date_key} rows={expected_rows:,} checkpoint valid")
            continue
        log(f"[run ] {idx}/{len(dates)} {date_key} rows={expected_rows:,} sources={','.join(sorted(day_truth['source'].unique()))}")
        try:
            process_date(date_key, day_partitions, parts_dir, args)
            done += 1
            elapsed = datetime.now() - start_time
            log(f"[done] {idx}/{len(dates)} {date_key} elapsed={str(elapsed).split('.')[0]}")
        except Exception as exc:
            failed.append({"date": date_key, "error": str(exc)})
            log(f"[fail] {idx}/{len(dates)} {date_key}: {exc}")

    if failed:
        pd.DataFrame(failed).to_csv(out_dir / "z_source_rebuild_failures.csv", index=False)
        raise SystemExit(f"Failed dates: {len(failed)}. See z_source_rebuild_failures.csv")

    log("Merging checkpoint parts into Overview CSV/XLSX")
    summary = merge_outputs(out_dir, parts_dir, truth, lake_root)
    summary.update(
        {
            "lake_root": str(lake_root),
            "out_dir": str(out_dir),
            "processed_dates": done,
            "skipped_dates": skipped,
        }
    )
    (out_dir / "z_source_rebuild_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log("Summary: " + json.dumps(summary))

    if not args.no_html:
        log("Generating Overview HTML")
        generate_html(out_dir, lake_root)
        log(f"HTML written: {out_dir / 'overview_dashboard.html'}")


if __name__ == "__main__":
    main()
