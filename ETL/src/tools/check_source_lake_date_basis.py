#!/usr/bin/env python3
"""Check whether lake source partitions are UTC-date or IST-date based."""

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
from ETL.src.tools.repair_overview_true_source import reader_sql

IST_OFFSET_SECONDS = 19_800


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check UTC vs IST lake partition date basis.")
    parser.add_argument("--lake-root", required=True)
    parser.add_argument("--sources", default="stream,fast")
    parser.add_argument("--dates", default="")
    parser.add_argument("--latest", type=int, default=5)
    parser.add_argument("--out", default="")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="8GB")
    return parser.parse_args()


def epoch_date_sql(offset_seconds: int = 0) -> str:
    return (
        "CAST(epoch_ms(CAST(FLOOR((TRY_CAST(reqTimeSec AS DOUBLE)"
        f" + {offset_seconds}) * 1000) AS BIGINT)) AS DATE)"
    )


def main() -> None:
    args = parse_args()
    root = Path(args.lake_root).expanduser().resolve()
    sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    partitions = lake_partitions.discover_partitions([root], sources=sources)
    if not partitions:
        raise SystemExit(f"No partitions found under {root}")

    requested_dates = [item.strip() for item in args.dates.split(",") if item.strip()]
    if requested_dates:
        dates = requested_dates
    else:
        dates = sorted({p.date_text for p in partitions})[-max(1, args.latest) :]

    rows = []
    con = duckdb.connect()
    con.execute(f"SET threads={max(1, int(args.threads))}")
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute("SET preserve_insertion_order=false")
    try:
        for date_text in dates:
            for source in sources:
                day_parts = [p for p in partitions if p.date_text == date_text and p.source == source]
                if not day_parts:
                    rows.append({"source": source, "partition_date": date_text, "status": "missing"})
                    continue

                reader = reader_sql(day_parts, lake_partitions)
                utc_date = epoch_date_sql(0)
                ist_date = epoch_date_sql(IST_OFFSET_SECONDS)
                summary = con.execute(
                    f"""
                    WITH base AS (
                        SELECT
                            TRY_CAST(reqTimeSec AS DOUBLE) AS sec,
                            {utc_date} AS utc_date,
                            {ist_date} AS ist_date
                        FROM {reader}
                        WHERE TRY_CAST(reqTimeSec AS DOUBLE) IS NOT NULL
                    )
                    SELECT
                        COUNT(*) AS rows_with_reqtime,
                        MIN(utc_date) AS min_utc_date,
                        MAX(utc_date) AS max_utc_date,
                        MIN(ist_date) AS min_ist_date,
                        MAX(ist_date) AS max_ist_date,
                        SUM(CASE WHEN CAST(utc_date AS VARCHAR) = '{date_text}' THEN 1 ELSE 0 END) AS utc_same_partition_rows,
                        SUM(CASE WHEN CAST(ist_date AS VARCHAR) = '{date_text}' THEN 1 ELSE 0 END) AS ist_same_partition_rows
                    FROM base
                    """
                ).fetchdf().iloc[0].to_dict()
                total = int(summary.get("rows_with_reqtime") or 0)
                utc_same = int(summary.get("utc_same_partition_rows") or 0)
                ist_same = int(summary.get("ist_same_partition_rows") or 0)
                rows.append(
                    {
                        "source": source,
                        "partition_date": date_text,
                        "status": "ok",
                        **summary,
                        "utc_same_pct": round((utc_same / total * 100), 4) if total else 0.0,
                        "ist_same_pct": round((ist_same / total * 100), 4) if total else 0.0,
                        "likely_basis": "UTC" if utc_same >= ist_same else "IST",
                    }
                )
    finally:
        con.close()

    result = pd.DataFrame(rows)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(out, index=False)
        print(f"Wrote {out}")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
