"""Wait for the 11-folder conversion, then create one deduplicated Parquet file."""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq


# Updated when the accelerated converter is launched.
CONVERTER_PID = 11912
CONVERTER_LOG = Path(r"D:\Vs - Code Work\PC2\convert_11_all_columns.log")
PARTS_DIR = Path(
    r"Z:\Vs - Code Work\ETL\data\raw\Veto Logs Backup\Veto Stream Backup\10\11_parquet"
)
DESTINATION_DIR = Path(r"Y:\Veto Logs Backup\aditya")
FINAL_FILE = DESTINATION_DIR / "11_final_clean.parquet"
TEMP_FILE = DESTINATION_DIR / "11_final_clean.parquet.tmp"
EXPECTED_PARTS = 50


def process_is_running(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def converter_succeeded() -> bool:
    try:
        text = CONVERTER_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "Conversion finished." in text and "Fatal batches: 0" in text


def main() -> None:
    print(f"Waiting for converter PID {CONVERTER_PID} ...", flush=True)
    while process_is_running(CONVERTER_PID):
        time.sleep(30)

    if not converter_succeeded():
        raise SystemExit(
            "Conversion process ended without a successful completion marker; merge not started."
        )

    parts = sorted(PARTS_DIR.glob("part_*.parquet"))
    if len(parts) != EXPECTED_PARTS:
        raise SystemExit(
            f"Expected {EXPECTED_PARTS} Parquet parts but found {len(parts)}; merge not started."
        )

    first_schema = pq.read_schema(parts[0])
    mismatched = [path.name for path in parts[1:] if pq.read_schema(path) != first_schema]
    if mismatched:
        raise SystemExit(
            f"Part schemas do not match ({len(mismatched)} mismatch(es)); merge not started."
        )

    DESTINATION_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_FILE.unlink(missing_ok=True)
    print(f"Merging {len(parts)} parts into {FINAL_FILE} ...", flush=True)

    connection = duckdb.connect()
    try:
        connection.execute("SET threads=12")
        connection.execute("SET memory_limit='28GB'")
        connection.execute("SET preserve_insertion_order=false")
        connection.execute("SET enable_progress_bar=true")
        connection.execute("SET enable_progress_bar_print=true")
        connection.execute(
            f"SET temp_directory='{(DESTINATION_DIR / 'duckdb_temp').as_posix()}'"
        )

        source_glob = (PARTS_DIR / "part_*.parquet").as_posix().replace("'", "''")
        temp_output = TEMP_FILE.as_posix().replace("'", "''")
        connection.execute(
            f"""
            COPY (
                SELECT *
                FROM read_parquet('{source_glob}', union_by_name=true)
            )
            TO '{temp_output}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD,
                COMPRESSION_LEVEL 3
            )
            """
        )
    finally:
        connection.close()

    final_schema = pq.read_schema(TEMP_FILE)
    if final_schema != first_schema:
        raise SystemExit("Final schema validation failed; temporary output was retained.")

    TEMP_FILE.replace(FINAL_FILE)
    print(f"Complete: {FINAL_FILE}", flush=True)
    print(f"Columns: {len(final_schema.names)}", flush=True)
    print(f"Size: {FINAL_FILE.stat().st_size / (1024 ** 3):.3f} GiB", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
