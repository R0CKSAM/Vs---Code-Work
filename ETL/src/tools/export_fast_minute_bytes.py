#!/usr/bin/env python3
"""Export exact FAST video bytes by IST minute for one platform and channel."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from build_concurrency import (
    DEFAULT_LAKE_FOLDER,
    configure_lake_selection,
    connect,
    minute_ist_sql,
    parquet_source_sql,
    platform_key_sql,
)
from vglive_core import channel_candidate_sql


ETL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT_DIR = ETL_ROOT / "output" / "exports"
DAILY_MART = (
    ETL_ROOT
    / "output"
    / "watch_hours"
    / "concurrency"
    / "fast_platform_channel_bandwidth_daily.parquet"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    date_group=parser.add_mutually_exclusive_group()
    date_group.add_argument("--date", help="One IST date in YYYY-MM-DD format.")
    date_group.add_argument("--start", help="First IST date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="Last IST date; required with --start.")
    parser.add_argument("--platform", default="samsung", help="Resolved FAST platform key.")
    parser.add_argument("--channel", default="India TV", help="Resolved channel name.")
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE_FOLDER)
    parser.add_argument("--archive-lake", action="append", default=[])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--memory-limit", default="16GB")
    parser.add_argument(
        "--allow-mart-mismatch",
        action="store_true",
        help="Publish source-Parquet totals when an older/incomplete daily mart disagrees.",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=ETL_ROOT / "output" / "cache" / "duckdb_temp",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start and not args.end:
        raise SystemExit("--end is required when --start is used.")
    if args.end and not args.start:
        raise SystemExit("--start is required when --end is used.")
    if args.date:
        start_date=end_date=datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.start:
        start_date=datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date=datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        start_date=end_date=date.today()-timedelta(days=1)
    if start_date > end_date:
        raise SystemExit("--start cannot be after --end.")
    args.start=start_date.isoformat()
    args.end=end_date.isoformat()
    args.source = "fast"
    args.lake = args.lake.expanduser().resolve()
    args.temp_dir = args.temp_dir.expanduser().resolve()
    configure_lake_selection(args)

    output = args.out or (
        DEFAULT_EXPORT_DIR
        / (
            f"india_tv_samsung_fast_bytes_minute_{args.start}.csv"
            if start_date == end_date else
            f"india_tv_samsung_fast_bytes_minute_{args.start}_to_{args.end}.csv"
        )
    )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    lake_source = parquet_source_sql(args.selected_lake_files)
    candidate = channel_candidate_sql("reqPath")
    minute = minute_ist_sql("reqTimeSec")
    platform = platform_key_sql("b.reqHost")
    output_sql = str(output).replace("'", "''")

    connection = connect(args)
    try:
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE selected_minute_bytes AS
            WITH base AS (
                SELECT
                    {minute} AS minute_ist,
                    lower(COALESCE(CAST(reqHost AS VARCHAR), '')) AS reqHost,
                    {candidate} AS candidate_id,
                    COALESCE(
                        NULLIF(regexp_replace(CAST(statusCode AS VARCHAR), '\\.0$', ''), ''),
                        'Unknown'
                    ) AS status_code,
                    TRY_CAST(totalBytes AS BIGINT) AS total_bytes
                FROM read_parquet({lake_source}, hive_partitioning=1, union_by_name=1)
                WHERE lower(COALESCE(CAST(source AS VARCHAR), 'fast')) = 'fast'
                  AND lower(COALESCE(CAST(reqPath AS VARCHAR), '')) LIKE '%.ts'
                  AND TRY_CAST(reqTimeSec AS DOUBLE) IS NOT NULL
            ),
            resolved AS (
                SELECT
                    b.*,
                    {platform} AS platform_key,
                    COALESCE(h.host_channel_name, p.path_channel_name, 'Other') AS channel_name
                FROM base b
                LEFT JOIN host_map h ON b.reqHost = h.reqHost
                LEFT JOIN path_map p ON b.candidate_id = p.candidate_id
            ),
            minute_totals AS (
                SELECT
                    minute_ist,
                    count(*)::BIGINT AS segment_rows,
                    count(*) FILTER (WHERE total_bytes IS NOT NULL)::BIGINT
                        AS rows_with_total_bytes,
                    CAST(sum(COALESCE(total_bytes, 0)) AS BIGINT) AS total_bytes,
                    CAST(sum(CASE WHEN status_code = '200' THEN COALESCE(total_bytes, 0) ELSE 0 END)
                        AS BIGINT) AS status_200_bytes,
                    CAST(sum(CASE WHEN status_code <> '200' THEN COALESCE(total_bytes, 0) ELSE 0 END)
                        AS BIGINT) AS non_200_bytes
                FROM resolved
                WHERE platform_key = ? AND lower(channel_name) = lower(?)
                  AND CAST(minute_ist AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
                GROUP BY minute_ist
            ),
            all_minutes AS (
                SELECT *
                FROM generate_series(
                    CAST(? AS DATE)::TIMESTAMP,
                    CAST(? AS DATE)::TIMESTAMP + INTERVAL '23 hours 59 minutes',
                    INTERVAL '1 minute'
                ) AS minutes(minute_ist)
            )
            SELECT
                'MINUTE' AS row_type,
                CAST(CAST(m.minute_ist AS DATE) AS VARCHAR) AS log_date,
                strftime(m.minute_ist, '%Y-%m-%d %H:%M') AS minute_ist,
                ? AS platform_key,
                ? AS channel_name,
                COALESCE(t.segment_rows, 0)::BIGINT AS segment_rows,
                COALESCE(t.rows_with_total_bytes, 0)::BIGINT AS rows_with_total_bytes,
                COALESCE(t.total_bytes, 0)::BIGINT AS total_bytes,
                round(COALESCE(t.total_bytes, 0) / 1048576.0, 3) AS total_mib,
                round(COALESCE(t.total_bytes, 0) / 1073741824.0, 6) AS total_gib,
                COALESCE(t.status_200_bytes, 0)::BIGINT AS status_200_bytes,
                COALESCE(t.non_200_bytes, 0)::BIGINT AS non_200_bytes
            FROM all_minutes m
            LEFT JOIN minute_totals t USING (minute_ist)
            ORDER BY m.minute_ist
            """,
            [
                args.platform,
                args.channel,
                args.start,
                args.end,
                args.start,
                args.end,
                args.platform,
                args.channel,
            ],
        )

        actual_rows = connection.execute(
            "SELECT log_date, sum(total_bytes), sum(segment_rows), sum(rows_with_total_bytes) "
            "FROM selected_minute_bytes GROUP BY log_date ORDER BY log_date"
        ).fetchall()
        expected_rows = connection.execute(
            """
            SELECT CAST(log_date AS VARCHAR), sum(total_bytes), sum(raw_ts_rows),
                   sum(rows_with_total_bytes)
            FROM read_parquet(?)
            WHERE CAST(log_date AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
              AND lower(platform_key) = lower(?)
              AND lower(channel_name) = lower(?)
            GROUP BY log_date
            ORDER BY log_date
            """,
            [str(DAILY_MART), args.start, args.end, args.platform, args.channel],
        ).fetchall()
        if not expected_rows:
            raise RuntimeError(
                f"No daily bandwidth mart rows matched {args.start} through {args.end}, "
                f"platform={args.platform}, channel={args.channel}."
            )
        normalized_actual=[(str(row[0]),*(int(value or 0) for value in row[1:])) for row in actual_rows]
        normalized_expected=[(str(row[0]),*(int(value or 0) for value in row[1:])) for row in expected_rows]
        mismatched_dates=[]
        expected_by_date={row[0]:row[1:] for row in normalized_expected}
        for row in normalized_actual:
            if expected_by_date.get(row[0]) != row[1:]:
                mismatched_dates.append(row[0])
        if mismatched_dates and not args.allow_mart_mismatch:
            raise RuntimeError(
                "Minute export did not reconcile by date: "
                f"actual={normalized_actual}, expected={normalized_expected}"
            )
        if mismatched_dates:
            print(
                "WARNING: using complete source-Parquet totals because the daily bandwidth "
                "mart is missing or stale for: " + ", ".join(mismatched_dates)
            )

        connection.execute(
            f"""
            COPY (
                SELECT * FROM selected_minute_bytes
                UNION ALL
                SELECT
                    'DAILY_TOTAL', log_date, log_date || ' TOTAL', ?, ?,
                    sum(segment_rows)::BIGINT,
                    sum(rows_with_total_bytes)::BIGINT,
                    sum(total_bytes)::BIGINT,
                    round(sum(total_bytes) / 1048576.0, 3),
                    round(sum(total_bytes) / 1073741824.0, 6),
                    sum(status_200_bytes)::BIGINT,
                    sum(non_200_bytes)::BIGINT
                FROM selected_minute_bytes
                GROUP BY log_date
            ) TO '{output_sql}' (FORMAT CSV, HEADER TRUE)
            """,
            [args.platform, args.channel],
        )
    finally:
        connection.close()

    print(f"Wrote {output}")
    print(
        f"{args.start} through {args.end} {args.channel} / {args.platform}: "
        f"{sum(row[1] for row in normalized_actual):,} bytes across "
        f"{sum(row[2] for row in normalized_actual):,} FAST .ts rows; "
        + (
            "source-Parquet totals published; stale mart dates were reported above."
            if mismatched_dates else
            "every daily minute total reconciles exactly to the bandwidth mart."
        )
    )


if __name__ == "__main__":
    main()
