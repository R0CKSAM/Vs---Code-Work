#!/usr/bin/env python3
"""
deviceSnapshotGenerator.py
Generate full-lake device intelligence CSVs from Veto stream logs.

Configure paths via --lake, --snapshot-csv, --daily-csv, or environment vars.
    py deviceSnapshotGenerator.py
"""

from __future__ import annotations

import logging
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import duckdb
    import psutil
    import pyarrow.parquet as pq
except ImportError as exc:
    raise SystemExit(
        f"Missing Python dependency: {exc.name}. Install ETL\\requirements.txt before running the pipeline."
    ) from exc


ETL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAKE_ROOT = Path(os.getenv("VG_ETL_LAKE_ROOT", str(ETL_ROOT / "data" / "lake")))
DEFAULT_CSV_OUT = Path(os.getenv("VG_DEVICE_SNAPSHOT_OUT", str(ETL_ROOT / "output" / "overview" / "device_snapshot.csv")))
DEFAULT_DAILY_CSV_OUT = Path(os.getenv("VG_DEVICE_DAILY_OUT", str(ETL_ROOT / "output" / "overview" / "device_daily.csv")))
IST_OFFSET_SECONDS = 19_800


def load_common_module(module_name: str, file_name: str):
    module_path = ETL_ROOT / "src" / "common" / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load common ETL helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_lake_partitions = load_common_module("veto_device_lake_partitions", "lake_partitions.py")
discover_lake_partitions = _lake_partitions.discover_partitions
parquet_globs = _lake_partitions.parquet_globs
resolve_lake_roots = _lake_partitions.resolve_lake_roots
_publication_dates = load_common_module("veto_device_publication_dates", "publication_dates.py")
DAILY_COLUMNS = [
    "source",
    "device_id",
    "utc_date",
    "rows_on_date",
    "distinct_ip",
    "distinct_ip_ua",
    "distinct_sessions",
]

logging.basicConfig(level=logging.INFO, format="  %(levelname)-7s %(message)s")
log = logging.getLogger("device_snapshot")


def get_conn() -> duckdb.DuckDBPyConnection:
    mem_avail = psutil.virtual_memory().available / (1024 ** 3)
    cpus = os.cpu_count() or 4
    mem_gb = max(4, min(int(mem_avail * 0.70), 48))
    threads = max(1, min(cpus // 4, 4))
    con = duckdb.connect()
    con.execute(f"SET threads={threads}")
    con.execute(f"SET memory_limit='{mem_gb}GB'")
    con.execute("SET preserve_insertion_order=false")
    try:
        con.execute("PRAGMA enable_progress_bar")
    except Exception:
        pass
    return con


def lake_reader_from_partitions(partitions: list) -> str:
    globs = parquet_globs(partitions)
    if not globs:
        raise SystemExit("No parquet partitions found for device snapshot refresh.")
    if len(globs) == 1:
        target = f"'{globs[0]}'"
    else:
        target = "[" + ", ".join(f"'{glob}'" for glob in globs) + "]"
    return f"read_parquet({target}, hive_partitioning=true, union_by_name=true)"


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def qs_extract(qs_col: str, param: str) -> str:
    extracted = f"NULLIF(regexp_extract(COALESCE({qs_col}, ''), '(?:^|[?&]){param}=([^&]*)', 1), '')"
    return f"CASE WHEN lower(trim({extracted})) IN ('null', 'nan', 'none', 'na') THEN NULL ELSE {extracted} END"


def ist_date_sql(epoch_expr: str) -> str:
    return (
        "CAST(epoch_ms(CAST(FLOOR(("
        f"TRY_CAST({epoch_expr} AS DOUBLE) + {IST_OFFSET_SECONDS}"
        ") * 1000) AS BIGINT)) AS DATE)"
    )


def latest_completed_ist_date() -> str:
    return _publication_dates.latest_completed_ist_date_text()


def log_step(step: int, total: int, message: str) -> None:
    bar_len = 24
    filled = round(bar_len * step / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    log.info(f"[{bar}] {step}/{total} {message}")


def csv_data_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as f:
        return max(0, sum(1 for _ in f) - 1)


def pa_schema_from_partitions(partitions: list) -> set[str]:
    cols: set[str] = set()
    skip = {"year", "month", "day"}
    preferred = {"queryStr", "cliIP", "UA"}
    for partition in partitions:
        for pf in partition.files:
            try:
                schema = pq.read_schema(pf)
                cols.update(name for name in schema.names if name not in skip)
            except Exception as exc:
                log.warning(f"Could not read parquet schema for {pf}: {exc}")
            if preferred <= cols:
                return cols
    return cols


def daily_manifest_path(daily_csv: Path) -> Path:
    return daily_csv.with_name(f"{daily_csv.stem}.manifest.json")


def load_daily_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        days = payload.get("days", payload) if isinstance(payload, dict) else {}
        return days if isinstance(days, dict) else {}
    except Exception as exc:
        log.warning(f"Could not read device daily manifest {path}: {exc}; refreshing affected dates.")
        return {}


def save_daily_manifest(path: Path, signatures: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"_{path.name}.tmp")
    payload = {
        "version": 2,
        "signature_basis": "parquet files grouped by lake year/month/day, using count, bytes, mtimes, and source-aware device_daily schema",
        "days": dict(sorted(signatures.items())),
    }
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    tmp.replace(path)


def partition_date_for_file(path: Path) -> str | None:
    values: dict[str, str] = {}
    for part in path.parts:
        if part.startswith("year="):
            values["year"] = part.split("=", 1)[1]
        elif part.startswith("month="):
            values["month"] = part.split("=", 1)[1]
        elif part.startswith("day="):
            values["day"] = part.split("=", 1)[1]
    if {"year", "month", "day"} <= values.keys():
        try:
            return f"{int(values['year']):04d}-{int(values['month']):02d}-{int(values['day']):02d}"
        except ValueError:
            return None
    return None


def lake_day_signatures(partitions: list) -> dict[str, dict]:
    signatures: dict[str, dict] = {}
    for partition in partitions:
        rec = signatures.setdefault(
            partition.date_text,
            {
                "files": 0,
                "bytes": 0,
                "rows": 0,
                "mtime_ns_sum": 0,
                "mtime_ns_max": 0,
                "sources": [],
            },
        )
        rec["sources"].append(partition.source)
        for parquet_file in partition.files:
            try:
                stat = parquet_file.stat()
                rec["files"] += 1
                rec["bytes"] += int(stat.st_size)
                rec["mtime_ns_sum"] += int(stat.st_mtime_ns)
                rec["mtime_ns_max"] = max(int(rec["mtime_ns_max"]), int(stat.st_mtime_ns))
                try:
                    rec["rows"] += int(pq.read_metadata(parquet_file).num_rows or 0)
                except Exception:
                    pass
            except FileNotFoundError:
                continue
    for rec in signatures.values():
        rec["sources"] = sorted(set(rec["sources"]))
    return dict(sorted(signatures.items()))


def comparable_day_signature(signature: dict | None) -> dict:
    """Ignore lake-root location so archiving does not trigger recomputation."""
    if not isinstance(signature, dict):
        return {}
    return {key: value for key, value in signature.items() if key != "roots"}


def existing_daily_dates(con: duckdb.DuckDBPyConnection, daily_csv: Path) -> set[str]:
    if not daily_csv.exists() or csv_data_lines(daily_csv) == 0:
        return set()
    rows = con.execute(f"""
        SELECT DISTINCT CAST(utc_date AS DATE)::VARCHAR AS utc_date
        FROM read_csv_auto('{sql_path(daily_csv)}', HEADER=true)
    """).fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def csv_has_column(path: Path, column: str) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            header = f.readline().strip()
        return column in {part.strip() for part in header.split(",")}
    except OSError:
        return False


def date_list_sql(dates: set[str]) -> str:
    if not dates:
        return ""
    return ", ".join(f"DATE '{date}'" for date in sorted(dates))


def write_empty_daily_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(DAILY_COLUMNS) + "\n", encoding="utf-8")


def replace_with_refreshed_daily(
    con: duckdb.DuckDBPyConnection,
    daily_csv: Path,
    refresh_csv: Path,
    merged_csv: Path,
    refreshed_dates: set[str],
    full_replace: bool = False,
) -> int:
    refresh_rows = csv_data_lines(refresh_csv)
    if full_replace or not daily_csv.exists():
        refresh_csv.replace(daily_csv)
        return refresh_rows

    if not refreshed_dates:
        return 0

    if merged_csv.exists():
        merged_csv.unlink()

    dates_sql = date_list_sql(refreshed_dates)
    existing_select = f"""
        SELECT *
        FROM read_csv_auto('{sql_path(daily_csv)}', HEADER=true)
        WHERE CAST(utc_date AS DATE) NOT IN ({dates_sql})
    """
    if refresh_rows:
        combined_select = f"""
            {existing_select}
            UNION ALL
            SELECT *
            FROM read_csv_auto('{sql_path(refresh_csv)}', HEADER=true)
        """
    else:
        combined_select = existing_select

    con.execute(f"""
        COPY (
            SELECT *
            FROM ({combined_select})
            ORDER BY CAST(utc_date AS DATE) DESC, rows_on_date DESC
        ) TO '{sql_path(merged_csv)}' (HEADER, DELIMITER ',');
    """)
    merged_csv.replace(daily_csv)
    return refresh_rows


def run_snapshot(
    lake_root: Path,
    snapshot_csv: Path,
    daily_csv: Path,
    start: str | None = None,
    end: str | None = None,
) -> None:
    daily_tmp = daily_csv.with_name("_device_daily_refresh.csv")
    daily_merged_tmp = daily_csv.with_name("_device_daily_merged.csv")
    manifest_path = daily_manifest_path(daily_csv)

    if not lake_root.is_dir():
        raise SystemExit(f"Lake folder not found: {lake_root}")

    previous_manifest_seed = load_daily_manifest(manifest_path)
    lake_roots = resolve_lake_roots(lake_root)
    cutoff_date = latest_completed_ist_date()
    scope_requested = bool(start or end)
    has_incremental_state = (
        daily_csv.exists()
        and bool(previous_manifest_seed)
        and csv_has_column(daily_csv, "source")
    )
    # A fresh or damaged state must scan the full lake. Scheduled runs with
    # healthy state only inspect the target date plus the repair lookback.
    scope_active = scope_requested and has_incremental_state
    partitions = discover_lake_partitions(
        lake_roots,
        sources=["fast", "stream"],
        start=start if scope_active else None,
        end=end if scope_active else None,
    )
    partitions = [partition for partition in partitions if partition.date_text <= cutoff_date]
    if not partitions:
        raise SystemExit(f"No completed winning lake partitions found from: {', '.join(str(root) for root in lake_roots)}")

    cols = pa_schema_from_partitions(partitions)
    required = {"queryStr"}
    missing = required - cols
    if missing:
        raise SystemExit(f"Missing required column(s): {', '.join(sorted(missing))}")

    has_ip = "cliIP" in cols
    has_ua = "UA" in cols
    has_source = True

    device_expr = qs_extract("queryStr", "device_id")
    session_expr = qs_extract("queryStr", "session_id")
    source_select = "LOWER(COALESCE(NULLIF(CAST(source AS VARCHAR), ''), 'stream')) AS source" if has_source else "'stream' AS source"
    ip_select = "cliIP" if has_ip else "NULL AS cliIP"
    ua_select = "UA" if has_ua else "NULL AS UA"
    ip_expr = "COUNT(DISTINCT cliIP)" if has_ip else "0"
    ipua_expr = "COUNT(DISTINCT (cliIP, UA))" if has_ip and has_ua else "0"
    # The lake is IST-partitioned. Use partition date for daily rollups so
    # device counts reconcile with Overview source rows exactly.
    ist_date_expr = "make_date(CAST(year AS INT), CAST(month AS INT), CAST(day AS INT))"

    daily_sql_template = """
        COPY (
            WITH base AS (
                SELECT
                    {source_select},
                    {device_expr} AS device_id,
                    {ist_date_expr} AS utc_date,
                    {ip_select},
                    {ua_select},
                    {session_expr} AS session_id
                FROM {reader}
                WHERE queryStr IS NOT NULL
                  AND queryStr LIKE '%device_id=%'
                  AND {device_expr} IS NOT NULL
                  {date_filter}
            )
            SELECT
                source,
                device_id,
                utc_date,
                COUNT(*) AS rows_on_date,
                {ip_expr} AS distinct_ip,
                {ipua_expr} AS distinct_ip_ua,
                COUNT(DISTINCT session_id) AS distinct_sessions
            FROM base
            GROUP BY source, device_id, utc_date
            ORDER BY utc_date DESC, source, rows_on_date DESC
        ) TO '{daily_out}' (HEADER, DELIMITER ',');
    """

    snapshot_sql = f"""
        COPY (
            SELECT
                device_id,
                MIN(CAST(utc_date AS DATE)) AS first_seen_utc_date,
                MAX(CAST(utc_date AS DATE)) AS last_seen_utc_date,
                COUNT(*) AS days_seen,
                SUM(rows_on_date) AS total_rows,
                SUM(distinct_ip) AS distinct_ip_day_sum,
                SUM(distinct_ip_ua) AS distinct_ip_ua_day_sum,
                SUM(distinct_sessions) AS distinct_sessions_day_sum
            FROM read_csv_auto('{sql_path(daily_csv)}', HEADER=true)
            GROUP BY device_id
            ORDER BY last_seen_utc_date DESC, total_rows DESC
        ) TO '{sql_path(snapshot_csv)}' (HEADER, DELIMITER ',');
    """

    log.info(f"Lake folder: {lake_root}")
    log.info("Resolved lake roots: " + " | ".join(str(root) for root in lake_roots))
    log.info(f"Latest completed IST date included: {cutoff_date}")
    log.info(f"Snapshot CSV: {snapshot_csv}")
    log.info(f"Daily CSV   : {daily_csv}")
    log.info(f"Manifest    : {manifest_path}")
    snapshot_csv.parent.mkdir(parents=True, exist_ok=True)
    daily_csv.parent.mkdir(parents=True, exist_ok=True)

    day_signatures = lake_day_signatures(partitions)
    current_dates = set(day_signatures)

    log_step(1, 5, "Schema checked and lake day signatures prepared")
    con = get_conn()
    try:
        previous_manifest = previous_manifest_seed
        csv_dates = existing_daily_dates(con, daily_csv)
        daily_has_source = csv_has_column(daily_csv, "source")

        full_replace = False
        if not day_signatures:
            log.info("No partition day signatures found; refreshing the full daily CSV.")
            refresh_dates = set()
            refresh_query_dates = set()
            date_filter = ""
            daily_needs_refresh = True
            full_replace = True
        elif not daily_csv.exists() or not previous_manifest or not daily_has_source:
            refresh_dates = current_dates
            refresh_query_dates = current_dates
            daily_needs_refresh = True
            full_replace = bool(daily_csv.exists() and not daily_has_source)
            date_filter = (
                f"AND {ist_date_expr} IN "
                f"({date_list_sql(refresh_query_dates)})"
            )
            if full_replace:
                log.info("Existing device_daily.csv is not source-aware; rebuilding it once.")
        else:
            changed_dates = {
                day
                for day, signature in day_signatures.items()
                if comparable_day_signature(previous_manifest.get(day)) != signature
            }
            removed_dates = (
                set()
                if scope_active
                else (set(previous_manifest) | csv_dates) - current_dates
            )
            refresh_dates = changed_dates | removed_dates
            refresh_query_dates = refresh_dates & current_dates
            daily_needs_refresh = bool(refresh_dates)
            date_filter = (
                f"AND {ist_date_expr} IN "
                f"({date_list_sql(refresh_query_dates)})"
                if refresh_query_dates
                else ""
            )

        if daily_needs_refresh:
            if refresh_dates:
                log.info(f"Refreshing {len(refresh_dates):,} device daily date(s).")
            daily_out = daily_tmp
        else:
            log.info("Device daily CSV already matches the lake manifest.")

        for tmp in (daily_tmp, daily_merged_tmp):
            if tmp.exists():
                tmp.unlink()

        if daily_needs_refresh:
            if refresh_query_dates or not day_signatures:
                query_partitions = [
                    partition for partition in partitions
                    if not refresh_query_dates or partition.date_text in refresh_query_dates
                ]
                query_reader = lake_reader_from_partitions(query_partitions)
                daily_sql = daily_sql_template.format(
                    source_select=source_select,
                    device_expr=device_expr,
                    session_expr=session_expr,
                    ip_select=ip_select,
                    ua_select=ua_select,
                    reader=query_reader,
                    date_filter=date_filter,
                    ist_date_expr=ist_date_expr,
                    ip_expr=ip_expr,
                    ipua_expr=ipua_expr,
                    daily_out=sql_path(daily_out),
                )
                log_step(2, 5, "Exporting refreshed device_daily rows")
                con.execute(daily_sql)
            else:
                write_empty_daily_csv(daily_tmp)
                log_step(2, 5, "Only removed dates detected; no new lake rows to export")

            refreshed_rows = replace_with_refreshed_daily(
                con,
                daily_csv=daily_csv,
                refresh_csv=daily_tmp,
                merged_csv=daily_merged_tmp,
                refreshed_dates=refresh_dates,
                full_replace=full_replace,
            )
            manifest_to_save = (
                {**previous_manifest, **day_signatures}
                if scope_active
                else day_signatures
            )
            save_daily_manifest(manifest_path, manifest_to_save)
            log_step(3, 5, f"Refreshed {refreshed_rows:,} daily rows")
        else:
            log_step(2, 5, "Daily CSV unchanged")
            log_step(3, 5, f"Current daily rows: {csv_data_lines(daily_csv):,}")

        log_step(4, 5, "Refreshing device_snapshot.csv from device_daily.csv")
        con.execute(snapshot_sql)
    finally:
        con.close()
        for tmp in (daily_tmp, daily_merged_tmp):
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    log_step(5, 5, "Device CSV generation complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate device snapshot CSVs.")
    parser.add_argument("--lake", default=str(DEFAULT_LAKE_ROOT))
    parser.add_argument("--snapshot-csv", default=str(DEFAULT_CSV_OUT))
    parser.add_argument("--daily-csv", default=str(DEFAULT_DAILY_CSV_OUT))
    parser.add_argument("--start", default=None, help="Optional IST date window start, YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="Optional IST date window end, YYYY-MM-DD.")
    args = parser.parse_args()

    run_snapshot(
        lake_root=Path(args.lake).expanduser().resolve(),
        snapshot_csv=Path(args.snapshot_csv).expanduser().resolve(),
        daily_csv=Path(args.daily_csv).expanduser().resolve(),
        start=args.start,
        end=args.end,
    )


if __name__ == "__main__":
    main()
