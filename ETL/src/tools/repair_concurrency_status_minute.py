#!/usr/bin/env python3
"""Repair missing concurrency status-minute history from the parquet lake.

This intentionally rebuilds only ``concurrency_status_minute.parquet``.  The
main concurrency minute and summary marts can already be correct while the
status split is incomplete because older runs predated the status mart.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

import build_concurrency as bc


DEFAULT_PARTS_DIR_NAME = "status_minute_repair_parts"


def date_days(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def part_path(parts_dir: Path, source: str, day: date) -> Path:
    return parts_dir / f"source={source.lower()}" / f"log_date={day.isoformat()}" / "status_minute.parquet"


def current_status_total(
    con: duckdb.DuckDBPyConnection,
    status_path: Path,
    source: str,
    day: date,
) -> int:
    if not status_path.exists():
        return 0
    return int(
        con.execute(
            f"""
            SELECT COALESCE(SUM(status_ts_rows), 0)::BIGINT
            FROM read_parquet('{bc.q(status_path)}')
            WHERE source = {bc.sql_text(source.lower())}
              AND log_date = {bc.sql_text(day.isoformat())}
            """
        ).fetchone()[0]
        or 0
    )


def target_minute_total(
    con: duckdb.DuckDBPyConnection,
    minute_path: Path,
    source: str,
    day: date,
) -> int:
    if not minute_path.exists():
        return 0
    return int(
        con.execute(
            f"""
            SELECT COALESCE(SUM(raw_ts_rows), 0)::BIGINT
            FROM read_parquet('{bc.q(minute_path)}')
            WHERE source = {bc.sql_text(source.lower())}
              AND log_date = {bc.sql_text(day.isoformat())}
            """
        ).fetchone()[0]
        or 0
    )


def build_status_part(
    con: duckdb.DuckDBPyConnection,
    lake: Path,
    source: str,
    day: date,
    out_path: Path,
) -> int:
    lake_glob = bc.q(lake / "**" / "*.parquet")
    candidate_expr = bc.channel_candidate_sql("reqPath")
    partition_filter = bc.date_filter_sql(day, day)
    platform_name = "'STREAM'" if source.lower() == "stream" else bc.platform_name_sql("b.reqHost")
    platform_key = "'stream'" if source.lower() == "stream" else bc.platform_key_sql("b.reqHost")

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE status_minute_repair_new AS
        WITH base AS (
            SELECT
                COALESCE(CAST(source AS VARCHAR), 'stream') AS source,
                strftime({bc.minute_ist_sql("reqTimeSec")}, '%Y-%m-%d') AS log_date,
                strftime({bc.minute_utc_sql("reqTimeSec")}, '%Y-%m-%d %H:%M:%S') AS minute_utc,
                strftime({bc.minute_ist_sql("reqTimeSec")}, '%Y-%m-%d %H:%M:%S') AS minute_ist,
                lower(COALESCE(reqHost, '')) AS reqHost,
                COALESCE(NULLIF(cliIP, ''), NULL) AS cliIP,
                NULLIF(trim(regexp_replace(COALESCE(CAST(UA AS VARCHAR), ''), '\\s+', ' ', 'g')), '') AS UA,
                COALESCE(NULLIF(regexp_replace(CAST(statusCode AS VARCHAR), '\\.0$', ''), ''), 'Unknown') AS statusCode,
                {candidate_expr} AS candidate_id
            FROM read_parquet('{lake_glob}', hive_partitioning=1, union_by_name=1)
            WHERE {bc.source_filter(source)}
              AND ({partition_filter})
              AND lower(COALESCE(reqPath, '')) LIKE '%.ts'
              AND TRY_CAST(reqTimeSec AS DOUBLE) IS NOT NULL
        ),
        resolved AS (
            SELECT
                b.*,
                COALESCE(h.host_channel_name, p.path_channel_name, 'Other') AS channel_name,
                {platform_name} AS platform_name,
                {platform_key} AS platform_key
            FROM base b
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
            statusCode AS status_code,
            COUNT(*)::BIGINT AS status_ts_rows,
            COUNT(DISTINCT cliIP)::BIGINT AS status_unique_viewers,
            COUNT(DISTINCT UA)::BIGINT AS status_unique_ua_viewers,
            ROUND(COUNT(*) / {bc.SEGMENTS_PER_MINUTE}, 3) AS status_segment_viewers_estimate
        FROM resolved
        GROUP BY 1,2,3,4,5,6,7,8,10
        """
    )

    rows = bc.table_count(con, "status_minute_repair_new")
    if rows <= 0:
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f"{out_path.stem}.tmp{out_path.suffix}")
    tmp_path.unlink(missing_ok=True)
    con.execute(
        f"COPY (SELECT * FROM status_minute_repair_new) TO '{bc.q(tmp_path)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    tmp_path.replace(out_path)
    return rows


def merge_parts(
    con: duckdb.DuckDBPyConnection,
    status_path: Path,
    parts_dir: Path,
    source: str,
    start: date,
    end: date,
) -> None:
    glob_path = parts_dir / f"source={source.lower()}" / "log_date=*" / "*.parquet"
    if not list((parts_dir / f"source={source.lower()}").glob("log_date=*/status_minute.parquet")):
        raise SystemExit(f"No repair parts found under {glob_path}")

    source_sql = bc.sql_text(source.lower())
    start_sql = bc.sql_text(start.isoformat())
    end_sql = bc.sql_text(end.isoformat())
    repair_parts_sql = f"""
        SELECT *
        FROM read_parquet('{bc.q(glob_path)}', hive_partitioning=1, union_by_name=1)
        WHERE source = {source_sql}
          AND log_date >= {start_sql}
          AND log_date <= {end_sql}
    """
    if status_path.exists():
        sql = f"""
            SELECT * FROM read_parquet('{bc.q(status_path)}')
            WHERE NOT (
                source = {source_sql}
                AND log_date >= {start_sql}
                AND log_date <= {end_sql}
            )
            UNION ALL
            {repair_parts_sql}
        """
    else:
        sql = repair_parts_sql
    bc.copy_table(con, sql, status_path)


def write_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair concurrency status-minute parquet history.")
    parser.add_argument("--lake", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=bc.DEFAULT_OUT_DIR)
    parser.add_argument("--source", choices=["fast", "stream"], required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="12GB")
    parser.add_argument("--temp-dir", type=Path, default=bc.ETL_ROOT / "output" / "cache" / "duckdb_temp")
    parser.add_argument("--force", action="store_true", help="Rebuild parts even when current totals already match.")
    parser.add_argument("--no-merge", action="store_true", help="Build day parts only; do not merge into the main status parquet.")
    args = parser.parse_args()

    args.lake = args.lake.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    if not args.lake.exists():
        raise SystemExit(f"Lake folder not found: {args.lake}")
    start = bc.parse_date(args.start)
    end = bc.parse_date(args.end)
    if start is None or end is None:
        raise SystemExit("Use --start and --end as YYYY-MM-DD.")
    if start > end:
        raise SystemExit("--start cannot be after --end.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    minute_path = args.out_dir / "concurrency_minute.parquet"
    status_path = args.out_dir / "concurrency_status_minute.parquet"
    parts_dir = args.out_dir / DEFAULT_PARTS_DIR_NAME
    con = bc.connect(args)
    built: list[dict] = []
    skipped: list[dict] = []
    try:
        for day in date_days(start, end):
            target_total = target_minute_total(con, minute_path, args.source, day)
            current_total = current_status_total(con, status_path, args.source, day)
            if not args.force and target_total > 0 and target_total == current_total:
                skipped.append({"date": day.isoformat(), "reason": "already_matches", "rows": current_total})
                print(f"[skip] {day.isoformat()} already matches ({current_total:,} rows)")
                continue
            out_path = part_path(parts_dir, args.source, day)
            rows = build_status_part(con, args.lake, args.source, day, out_path)
            built_total = int(
                con.execute(
                    f"SELECT COALESCE(SUM(status_ts_rows), 0)::BIGINT FROM read_parquet('{bc.q(out_path)}')"
                ).fetchone()[0]
                or 0
            ) if rows else 0
            built.append(
                {
                    "date": day.isoformat(),
                    "part_rows": rows,
                    "target_ts_rows": target_total,
                    "built_ts_rows": built_total,
                    "part": str(out_path),
                }
            )
            print(
                f"[part] {day.isoformat()} rows={rows:,} "
                f"ts_rows={built_total:,} target={target_total:,}"
            )
            if target_total and built_total != target_total:
                raise SystemExit(
                    f"Repair part mismatch for {day.isoformat()}: "
                    f"built {built_total:,}, target {target_total:,}"
                )

        if not args.no_merge:
            missing_parts = [
                day.isoformat()
                for day in date_days(start, end)
                if target_minute_total(con, minute_path, args.source, day) > 0
                and current_status_total(con, status_path, args.source, day) != target_minute_total(con, minute_path, args.source, day)
                and not part_path(parts_dir, args.source, day).exists()
            ]
            if missing_parts:
                raise SystemExit("Missing repair parts; refusing merge: " + ", ".join(missing_parts[:20]))
            merge_parts(con, status_path, parts_dir, args.source, start, end)
            print(f"[merge] updated {status_path}")
    finally:
        con.close()

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "lake": str(args.lake),
        "out_dir": str(args.out_dir),
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "built": built,
        "skipped": skipped,
        "merged": not args.no_merge,
    }
    write_manifest(args.out_dir / "concurrency_status_minute_repair_manifest.json", manifest)
    print(json.dumps({"built_days": len(built), "skipped_days": len(skipped), "merged": not args.no_merge}, indent=2))


if __name__ == "__main__":
    main()
