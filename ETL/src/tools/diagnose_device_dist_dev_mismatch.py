#!/usr/bin/env python3
"""Diagnose distinct device_id mismatches for source-date partitions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ETL.src.common import lake_partitions
from ETL.src.tools.repair_overview_true_source import qs_extract, reader_sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List raw device_id values counted by Overview but absent from device_daily.")
    parser.add_argument("--lake-root", required=True)
    parser.add_argument("--dates", required=True)
    parser.add_argument("--source", default="stream")
    parser.add_argument("--device-daily", default=str(Path("ETL") / "output" / "overview_z_source_rebuild" / "device_daily.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = [item.strip() for item in args.dates.split(",") if item.strip()]
    partitions = lake_partitions.discover_partitions(
        [Path(args.lake_root).expanduser().resolve()],
        sources=[args.source],
        start=min(dates),
        end=max(dates),
    )
    daily = pd.read_csv(args.device_daily)
    daily["source"] = daily["source"].astype(str).str.lower()
    daily["utc_date"] = daily["utc_date"].astype(str).str[:10]
    daily["device_id"] = daily["device_id"].astype(str)

    con = duckdb.connect()
    try:
        for date_text in dates:
            day_parts = [p for p in partitions if p.date_text == date_text and p.source == args.source]
            reader = reader_sql(day_parts, lake_partitions)
            device_id = qs_extract("queryStr", "device_id")
            raw = con.execute(
                f"""
                SELECT
                    {device_id} AS device_id,
                    COUNT(*) AS rows
                FROM {reader}
                GROUP BY 1
                HAVING {device_id} IS NOT NULL
                ORDER BY rows DESC
                """
            ).fetchdf()
            raw["device_id_text"] = raw["device_id"].astype(str)
            kept = set(
                daily[
                    (daily["source"] == args.source)
                    & (daily["utc_date"] == date_text)
                ]["device_id"].astype(str)
            )
            raw["in_device_daily"] = raw["device_id_text"].isin(kept)
            raw["lower"] = raw["device_id_text"].str.lower()
            missing = raw[~raw["in_device_daily"]]
            print(f"\n{args.source} {date_text}")
            print(
                "raw_distinct=",
                int(raw["device_id_text"].nunique()),
                "kept_distinct=",
                int(raw["in_device_daily"].sum()),
                "nan_text_distinct=",
                int(raw["lower"].eq("nan").sum()),
            )
            print(missing.head(50).to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
