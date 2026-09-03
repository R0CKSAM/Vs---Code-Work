#!/usr/bin/env python3
"""Build minute-level identity aggregates from .ts playback rows."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from build_concurrency import (
    DEFAULT_LAKE_FOLDER,
    DEFAULT_OUT_DIR,
    add_archive_lake_argument,
    checked_dates,
    configure_lake_selection,
    connect,
    date_filter_sql,
    lake_manifest_fields,
    minute_ist_sql,
    minute_utc_sql,
    parquet_source_sql,
    platform_key_sql,
    platform_name_sql,
    q,
    source_filter,
    table_count,
    write_append_table,
)
from vglive_core import channel_candidate_sql


def query_param_sql(param_name: str, query_col: str = "queryStr") -> str:
    return f"regexp_extract(COALESCE(CAST({query_col} AS VARCHAR), ''), '(?i)(?:^|[?&]){param_name}=([^&]+)', 1)"


def decoded_query_param_sql(param_name: str, query_col: str = "queryStr") -> str:
    raw_value = query_param_sql(param_name, query_col)
    return f"COALESCE(try(url_decode(NULLIF({raw_value}, ''))), NULLIF({raw_value}, ''))"


def normalized_identity_sql(param_name: str) -> str:
    return f"NULLIF(trim(CAST({decoded_query_param_sql(param_name)} AS VARCHAR)), '')"


def resolved_platform_name_sql(source: str) -> str:
    # STREAM .ts rows do not reliably carry platform on every request. Keep the
    # minute mart source/channel scoped instead of publishing partial platform splits.
    if source.lower() == "stream":
        return "'STREAM'"
    return platform_name_sql("reqHost")


def resolved_platform_key_sql(source: str) -> str:
    if source.lower() == "stream":
        return "'stream'"
    return platform_key_sql("reqHost")


def build_identity_minute_table(
    con,
    args: argparse.Namespace,
    start: date | None = None,
    end: date | None = None,
) -> None:
    configured_start, configured_end = checked_dates(args)
    start = configured_start if start is None else start
    end = configured_end if end is None else end
    lake_source = parquet_source_sql(args.selected_lake_files)
    partition_filter = date_filter_sql(start, end)
    candidate_expr = channel_candidate_sql("reqPath")
    session_expr = normalized_identity_sql("session_id")
    device_expr = normalized_identity_sql("device_id")

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE identity_minute_new AS
        WITH base AS (
            SELECT
                COALESCE(CAST(source AS VARCHAR), '{args.source.lower()}') AS source,
                strftime({minute_ist_sql("reqTimeSec")}, '%Y-%m-%d') AS log_date,
                strftime({minute_utc_sql("reqTimeSec")}, '%Y-%m-%d %H:%M:%S') AS minute_utc,
                strftime({minute_ist_sql("reqTimeSec")}, '%Y-%m-%d %H:%M:%S') AS minute_ist,
                lower(COALESCE(reqHost, '')) AS reqHost,
                COALESCE(NULLIF(cliIP, ''), NULL) AS cliIP,
                NULLIF(trim(regexp_replace(COALESCE(CAST(UA AS VARCHAR), ''), '\\s+', ' ', 'g')), '') AS UA,
                COALESCE(NULLIF(regexp_replace(CAST(statusCode AS VARCHAR), '\\.0$', ''), ''), 'Unknown') AS statusCode,
                lower(COALESCE(CAST(reqPath AS VARCHAR), '')) LIKE '%.ts' AS is_ts,
                {session_expr} AS session_id,
                {device_expr} AS device_id,
                {candidate_expr} AS candidate_id,
                {resolved_platform_name_sql(args.source)} AS platform_name,
                {resolved_platform_key_sql(args.source)} AS platform_key
            FROM read_parquet({lake_source}, hive_partitioning=1, union_by_name=1)
            WHERE {source_filter(args.source)}
              AND ({partition_filter})
              AND (
                  lower(COALESCE(CAST(reqPath AS VARCHAR), '')) LIKE '%.ts'
                  OR COALESCE(CAST(queryStr AS VARCHAR), '') LIKE '%session_id=%'
                  OR COALESCE(CAST(queryStr AS VARCHAR), '') LIKE '%device_id=%'
              )
              AND TRY_CAST(reqTimeSec AS DOUBLE) IS NOT NULL
        ),
        resolved AS (
            SELECT
                b.*,
                COALESCE(
                    hc.host_candidate_channel_name,
                    h.host_channel_name,
                    p.path_channel_name,
                    'Other'
                ) AS channel_name
            FROM base b
            LEFT JOIN host_candidate_map hc
                ON b.reqHost = hc.reqHost AND b.candidate_id = hc.candidate_id
            LEFT JOIN host_map h ON b.reqHost = h.reqHost
            LEFT JOIN path_map p ON b.candidate_id = p.candidate_id
        )
        SELECT
            log_date,
            source,
            minute_utc,
            minute_ist,
            platform_key,
            platform_name,
            candidate_id,
            channel_name,
            any_value(reqHost ORDER BY reqHost) AS reqHost,
            COUNT(DISTINCT reqHost)::BIGINT AS distinct_hosts,
            COUNT(*) FILTER (WHERE is_ts)::BIGINT AS raw_ts_rows,
            COUNT(*) FILTER (WHERE is_ts AND statusCode = '200')::BIGINT AS status_200_ts_rows,
            COUNT(DISTINCT CASE WHEN is_ts THEN cliIP ELSE NULL END)::BIGINT AS distinct_cliips,
            COUNT(DISTINCT CASE
                WHEN is_ts AND (cliIP IS NOT NULL OR UA IS NOT NULL) THEN COALESCE(cliIP, '') || '|' || COALESCE(UA, '')
                ELSE NULL
            END)::BIGINT AS distinct_ipua_pairs,
            COUNT(DISTINCT device_id)::BIGINT AS distinct_devices,
            COUNT(DISTINCT session_id)::BIGINT AS distinct_sessions
        FROM resolved
        GROUP BY 1,2,3,4,5,6,7,8
        """
    )


def daily_ranges(start: date | None, end: date | None) -> list[tuple[date | None, date | None]]:
    """Split bounded rebuilds into daily scans to cap DISTINCT aggregation memory."""
    if start is None or end is None:
        return [(start, end)]
    ranges: list[tuple[date | None, date | None]] = []
    current = start
    while current <= end:
        ranges.append((current, current))
        current += timedelta(days=1)
    return ranges


def write_manifest(args: argparse.Namespace, new_rows: int, output_path: Path) -> None:
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "lake": str(args.lake.resolve()),
        **lake_manifest_fields(args),
        "output": str(output_path.resolve()),
        "date_range_replaced": {"start": args.start or "", "end": args.end or ""},
        "metric_notes": {
            "distinct_cliips": "Distinct cliIP values per IST minute on .ts playback rows.",
            "distinct_ipua_pairs": "Distinct cliIP + normalized UA signatures per IST minute on .ts playback rows.",
            "distinct_devices": "Distinct STREAM device_id values per IST minute where queryStr carries device_id.",
            "distinct_sessions": "Distinct STREAM session_id values per IST minute where queryStr carries session_id.",
        },
        "new_rows": new_rows,
    }
    output_path.with_name("identity_minute_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build minute-level identity aggregates.")
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE_FOLDER)
    add_archive_lake_argument(parser)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--source", choices=["fast", "stream"], required=True)
    parser.add_argument("--start", default=None, help="IST lake date start, YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="IST lake date end, YYYY-MM-DD.")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--memory-limit", default="16GB")
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "output" / "cache" / "duckdb_temp",
    )
    args = parser.parse_args()

    args.lake = args.lake.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    if not args.lake.exists():
        raise SystemExit(f"Lake folder not found: {args.lake}")

    start, end = checked_dates(args)
    configure_lake_selection(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    con = connect(args)
    try:
        new_rows = 0
        has_accumulator = False
        for chunk_start, chunk_end in daily_ranges(start, end):
            build_identity_minute_table(con, args, chunk_start, chunk_end)
            chunk_rows = table_count(con, "identity_minute_new")
            chunk_label = (
                chunk_start.isoformat()
                if chunk_start is not None
                else "all available dates"
            )
            print(f"Identity minute chunk {chunk_label}: {chunk_rows:,} rows")
            if chunk_rows <= 0:
                continue
            if has_accumulator:
                con.execute("INSERT INTO identity_minute_all SELECT * FROM identity_minute_new")
            else:
                con.execute(
                    "CREATE OR REPLACE TEMP TABLE identity_minute_all AS "
                    "SELECT * FROM identity_minute_new"
                )
                has_accumulator = True
            new_rows += chunk_rows
            con.execute("DROP TABLE identity_minute_new")

        if not has_accumulator:
            raise SystemExit(f"No {args.source.upper()} .ts rows found for the selected identity-minute range.")

        output_path = args.out_dir / "identity_minute.parquet"
        write_append_table(con, "identity_minute_all", output_path, args.source, start, end)
        write_manifest(args, new_rows, output_path)
    finally:
        con.close()

    print(f"Identity minute parquet: {output_path}")
    print(json.dumps({"source": args.source, "new_rows": new_rows}, indent=2))


if __name__ == "__main__":
    main()
