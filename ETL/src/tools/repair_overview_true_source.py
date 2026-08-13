#!/usr/bin/env python3
"""Repair Overview rows from the true lake partitions.

This tool is intentionally narrow: it compares Overview source rows with the
resolved current+archive lake metadata, then scans only mismatched completed
dates. It is safer than rerunning the full Overview query over every partition.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import pyarrow.parquet as pq


SRC_ROOT = Path(__file__).resolve().parents[1]
ETL_ROOT = SRC_ROOT.parent


def load_overview_module():
    path = SRC_ROOT / "overview" / "overViewGenerator.py"
    spec = importlib.util.spec_from_file_location("overview_generator_repair", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Overview generator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_lake_helpers():
    path = SRC_ROOT / "common" / "lake_partitions.py"
    spec = importlib.util.spec_from_file_location("lake_partitions_repair", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load lake helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def partition_row_count(partition) -> int:
    total = 0
    for file in partition.files:
        total += int(pq.read_metadata(file).num_rows or 0)
    return total


def completed_truth_rows(partitions: Iterable, cutoff: str) -> pd.DataFrame:
    rows = []
    for partition in partitions:
        if partition.date_text > cutoff:
            continue
        rows.append(
            {
                "source": partition.source,
                "date": partition.date_text,
                "rows_true": partition_row_count(partition),
                "files": len(partition.files),
                "root": str(partition.root),
            }
        )
    return pd.DataFrame(rows)


def reader_sql(partitions: list, lake_helpers) -> str:
    globs = lake_helpers.parquet_globs(partitions)
    if not globs:
        raise ValueError("No parquet partitions selected for repair.")
    if len(globs) == 1:
        target = f"'{globs[0]}'"
    else:
        target = "[" + ", ".join(f"'{glob}'" for glob in globs) + "]"
    return f"read_parquet({target}, hive_partitioning=true, union_by_name=true)"


def qs_extract(qs_col: str, param: str) -> str:
    # Accept both raw query strings (a=1&b=2) and URL-style strings (?a=1&b=2).
    extracted = f"NULLIF(regexp_extract(COALESCE({qs_col}, ''), '(?:^|[?&]){param}=([^&]*)', 1), '')"
    # Literal placeholders are not real identities. Counting device_id=null as
    # one device caused Overview to disagree with rebuilt device_daily files.
    return f"CASE WHEN lower(trim({extracted})) IN ('null', 'nan', 'none', 'na') THEN NULL ELSE {extracted} END"

def exact_query(con, reader: str, *, group_source: bool) -> pd.DataFrame:
    source_select = ", lower(COALESCE(CAST(source AS VARCHAR), 'stream')) AS source" if group_source else ""
    source_group = ", source" if group_source else ""
    session_id = qs_extract("queryStr", "session_id")
    device_id = qs_extract("queryStr", "device_id")
    sess_present = "SUM(CASE WHEN COALESCE(queryStr, '') LIKE '%session_id=%' THEN 1 ELSE 0 END)"
    sess_blank = (
        "SUM(CASE WHEN COALESCE(queryStr, '') LIKE '%session_id=%' "
        f"AND {session_id} IS NULL THEN 1 ELSE 0 END)"
    )
    sess_none = (
        "SUM(CASE WHEN queryStr IS NULL "
        "OR COALESCE(queryStr, '') NOT LIKE '%session_id=%' THEN 1 ELSE 0 END)"
    )
    return con.execute(
        f"""
        SELECT
            make_date(CAST(year AS INT), CAST(month AS INT), CAST(day AS INT)) AS partition_date
            {source_select},
            COUNT(*) AS total_rows,
            COUNT(cliIP) AS ip_rows,
            COUNT(DISTINCT cliIP) AS distinct_ip,
            COUNT(DISTINCT (cliIP, UA)) AS distinct_ipua,
            SUM(TRY_CAST(totalBytes AS DOUBLE)) AS total_bytes,
            COUNT(DISTINCT {device_id}) AS distinct_dev,
            COUNT(DISTINCT {session_id}) AS distinct_sess,
            ({sess_present} - {sess_blank}) AS sess_avail,
            {sess_blank} AS sess_na,
            {sess_none} AS sess_none
        FROM {reader}
        GROUP BY year, month, day{source_group}
        ORDER BY partition_date{source_group}
        """
    ).df()


def source_rows_from_df(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        date_key = pd.to_datetime(row["partition_date"]).strftime("%Y-%m-%d")
        ip_rows = int(row["ip_rows"] or 0)
        dist_ip = int(row["distinct_ip"] or 0)
        dist_ipua = int(row["distinct_ipua"] or 0)
        sess_avail = int(row["sess_avail"] or 0)
        sess_na = int(row["sess_na"] or 0)
        sess_none = int(row["sess_none"] or 0)
        bytes_gib = float(row["total_bytes"] or 0) / (1024 ** 3)
        rows.append(
            {
                "source": str(row.get("source", "stream") or "stream").lower(),
                "date": date_key,
                "bytes": round(bytes_gib, 2),
                "rows": int(row["total_rows"] or 0),
                "ip_rows": ip_rows,
                "dist_ip": dist_ip,
                "dist_ipua": dist_ipua,
                "dist_dev": int(row["distinct_dev"] or 0),
                "dist_sess": int(row["distinct_sess"] or 0),
                "dist_ip_r2": dist_ip,
                "dist_ipua_r2": dist_ipua,
                "sess_avail": sess_avail,
                "sess_na": sess_na,
                "sess_none": sess_none,
                "pct_ip": round(dist_ip / ip_rows, 6) if ip_rows else 0,
                "pct_ipua": round(dist_ipua / ip_rows, 6) if ip_rows else 0,
                "pct_sess": round(sess_avail / ip_rows, 6) if ip_rows else 0,
                "pct_sessna": round(sess_na / ip_rows, 6) if ip_rows else 0,
                "pct_none": round(sess_none / ip_rows, 6) if ip_rows else 0,
            }
        )
    return rows


def overview_rows_from_df(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        date_key = pd.to_datetime(row["partition_date"]).strftime("%Y-%m-%d")
        ip_rows = int(row["ip_rows"] or 0)
        bytes_gib = float(row["total_bytes"] or 0) / (1024 ** 3)
        rows.append(
            {
                "ist_date": datetime.strptime(date_key, "%Y-%m-%d").strftime("%d/%m/%y"),
                "bytes_gib": round(bytes_gib, 2),
                "total_rows": int(row["total_rows"] or 0),
                "ip_rows": ip_rows,
                "dist_ip": int(row["distinct_ip"] or 0),
                "dist_ip_ua": int(row["distinct_ipua"] or 0),
                "dist_dev": int(row["distinct_dev"] or 0),
                "dist_sess": int(row["distinct_sess"] or 0),
                "sess_avail": int(row["sess_avail"] or 0),
                "sess_na": int(row["sess_na"] or 0),
                "sess_none": int(row["sess_none"] or 0),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair Overview from true lake source for mismatched dates.")
    parser.add_argument("--lake-root", default=str(ETL_ROOT / "data" / "lake"))
    parser.add_argument("--out-dir", default=str(ETL_ROOT / "output" / "overview"))
    parser.add_argument("--sources", default="fast,stream")
    parser.add_argument("--dates", default="", help="Optional comma-separated YYYY-MM-DD dates to repair.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ov = load_overview_module()
    lake_helpers = load_lake_helpers()

    lake_root = Path(args.lake_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    cutoff = ov.latest_completed_ist_date()

    roots = lake_helpers.resolve_lake_roots(lake_root)
    partitions = lake_helpers.discover_partitions(roots, sources=sources)
    truth = completed_truth_rows(partitions, cutoff)
    source_csv = out_dir / ov.SOURCE_DAILY_FILENAME
    current = pd.read_csv(source_csv)
    current["source"] = current["source"].astype(str).str.lower()
    current["date"] = current["date"].astype(str).str[:10]

    merged = truth.merge(
        current[["source", "date", "rows"]].rename(columns={"rows": "rows_overview"}),
        on=["source", "date"],
        how="outer",
    )
    merged["rows_true"] = merged["rows_true"].fillna(0).astype("int64")
    merged["rows_overview"] = merged["rows_overview"].fillna(0).astype("int64")
    merged["diff"] = merged["rows_overview"] - merged["rows_true"]
    mismatched = merged[merged["diff"] != 0].copy()
    if args.dates:
        requested = {item.strip() for item in args.dates.split(",") if item.strip()}
        repair_dates = sorted(requested)
        mismatched = mismatched[mismatched["date"].isin(requested)]
    else:
        repair_dates = sorted(set(mismatched["date"].dropna().astype(str)))
    audit_dir = out_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mismatch_path = audit_dir / f"overview_true_source_mismatches_{stamp}.csv"
    mismatched.to_csv(mismatch_path, index=False)
    print(f"Mismatch audit written: {mismatch_path}")

    if not repair_dates:
        print("No completed-date Overview source mismatches found.")
        return

    print("Repair dates:", ", ".join(repair_dates))
    selected = [p for p in partitions if p.date_text in set(repair_dates)]
    if args.dry_run:
        print(f"Dry run only. Would scan {len(selected)} partition(s).")
        return

    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='8GB'")
    con.execute("SET preserve_insertion_order=false")
    # Targeted repairs can still spill on a high-volume completed day. Honour the
    # pipeline scratch settings so a constrained local ETL drive is not the limit.
    temp_dir = os.getenv("VG_DUCKDB_TEMP_DIR")
    if temp_dir:
        temp_path = Path(temp_dir).expanduser().resolve()
        temp_path.mkdir(parents=True, exist_ok=True)
        safe_temp_path = str(temp_path).replace("'", "''")
        con.execute(f"SET temp_directory='{safe_temp_path}'")
    max_temp_size = os.getenv("VG_DUCKDB_MAX_TEMP_SIZE")
    if max_temp_size:
        safe_max_temp_size = str(max_temp_size).replace("'", "''")
        con.execute(f"SET max_temp_directory_size='{safe_max_temp_size}'")
    try:
        reader = reader_sql(selected, lake_helpers)
        exact_source_df = exact_query(con, reader, group_source=True)
        exact_date_df = exact_query(con, reader, group_source=False)
    finally:
        con.close()

    exact_source_rows = source_rows_from_df(exact_source_df)
    exact_overview_rows = overview_rows_from_df(exact_date_df)

    repaired_keys = {(row["source"], row["date"]) for row in exact_source_rows}
    kept_source = [
        row.to_dict()
        for _, row in current.iterrows()
        if (str(row["source"]).lower(), str(row["date"])[:10]) not in repaired_keys
    ]
    repaired_source = kept_source + exact_source_rows
    repaired_source.sort(key=lambda row: (str(row.get("date", "")), str(row.get("source", ""))))
    ov.write_source_rows_csv(source_csv, repaired_source)

    output_file = out_dir / ov.OVERVIEW_FILENAME
    old_rows = ov.load_existing_rows(output_file)
    repaired_ist_dates = {row["ist_date"] for row in exact_overview_rows}
    all_rows = [row for row in old_rows if row.get("ist_date") not in repaired_ist_dates]
    all_rows.extend(exact_overview_rows)
    all_rows.sort(key=lambda row: datetime.strptime(row["ist_date"], "%d/%m/%y"))

    true_total_rows = int(truth["rows_true"].sum()) if not truth.empty else 0
    true_total_files = int(truth["files"].sum()) if not truth.empty else 0
    date_range_ist, time_range_ist = ov.mart_date_ranges(all_rows)
    ov.write_overview_excel(
        output_path=output_file,
        data_rows=all_rows,
        lake_root=lake_root,
        year_filter=None,
        month_filter=None,
        total_rows_pa=true_total_rows,
        total_files=true_total_files,
        date_range_ist=date_range_ist,
        time_range_ist=time_range_ist,
    )

    exact_source_df.to_csv(audit_dir / f"overview_true_source_repaired_source_{stamp}.csv", index=False)
    exact_date_df.to_csv(audit_dir / f"overview_true_source_repaired_dates_{stamp}.csv", index=False)
    print(f"Repaired Overview source rows: {len(exact_source_rows):,}")
    print(f"Repaired Overview day rows   : {len(exact_overview_rows):,}")
    print(f"Overview Excel written       : {output_file}")


if __name__ == "__main__":
    main()
