"""
VETO Stream Time Calculator
Counts .ts segment delivery rows in VETO's parquet log lake over a date
range and converts to total streaming hours.

Usage:
    python a2x.py "Z:/Veto Logs Backup/DO NOT DELETE"
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyarrow.parquet as pq
import pyarrow.compute as pc

# =========================
# CONFIG
# =========================

SECONDS_PER_TS = 6
TS_COLUMN = "reqPath"      # confirmed column that holds the .ts / .m3u8 request path
MAX_WORKERS = 8            # parallel file reads per day


# =========================
# FUNCTIONS
# =========================

def get_date(prompt):
    while True:
        value = input(prompt).strip()
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date. Use YYYY-MM-DD")
            print("Example: 2026-08-16")


def count_ts_rows(file):
    """
    Reads only the TS_COLUMN from a parquet file (columnar projection —
    skips decoding every other field) and counts rows ending in '.ts'
    using Arrow's vectorized compute kernels (no Python-level loop).
    """
    try:
        table = pq.read_table(file, columns=[TS_COLUMN])
    except Exception as e:
        print(f"  ERROR reading {file.name}: {e}")
        return 0

    col = table.column(TS_COLUMN)
    if col.type != "string":
        col = pc.cast(col, "string")

    mask = pc.ends_with(col, ".ts")
    total = pc.sum(mask).as_py()
    return total or 0


def process_day(parquet_files):
    """
    Processes all files for one day concurrently. Arrow's parquet
    decode releases the GIL, so a thread pool gives real parallelism
    here (not just I/O-wait overlap) — this matters most when the
    lake root is a network share.
    """
    day_total = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(count_ts_rows, f): f for f in parquet_files}
        for fut in as_completed(futures):
            day_total += fut.result()
    return day_total


# =========================
# MAIN
# =========================

if len(sys.argv) < 2:
    print()
    print("Usage:")
    print('python a3x.py "Z:/Veto Logs Backup/DO NOT DELETE"')
    print()
    sys.exit(1)

root = Path(sys.argv[1])

if not root.exists():
    print()
    print("ROOT PATH NOT FOUND:")
    print(root)
    sys.exit(1)

print()
print("==========================================")
print("     VETO STREAM TIME CALCULATOR")
print("==========================================")
print()
print("Lake Root:")
print(root)
print()

start_date = get_date("Start Date (YYYY-MM-DD): ")
end_date = get_date("End Date   (YYYY-MM-DD): ")

if end_date < start_date:
    print()
    print("ERROR: End date cannot be before start date.")
    sys.exit(1)

print()
print("==========================================")
print(f"Processing {start_date} to {end_date}")
print("==========================================")
print()

current_date = start_date
grand_total_ts = 0
grand_total_files = 0
days_found = 0

while current_date <= end_date:

    day_folder = (
        root
        / "source=stream"
        / f"year={current_date.year:04d}"
        / f"month={current_date.month:02d}"
        / f"day={current_date.day:02d}"
    )

    print(f"[{current_date}]")

    if not day_folder.exists():
        print("  Folder not found")
        print()
        current_date += timedelta(days=1)
        continue

    parquet_files = list(day_folder.glob("*.parquet"))

    if not parquet_files:
        print("  No parquet files")
        print()
        current_date += timedelta(days=1)
        continue

    days_found += 1
    grand_total_files += len(parquet_files)

    day_ts = process_day(parquet_files)
    grand_total_ts += day_ts

    day_hours = (day_ts * SECONDS_PER_TS) / 3600

    print(f"  Files     : {len(parquet_files):,}")
    print(f"  .TS Rows  : {day_ts:,}")
    print(f"  Hours     : {day_hours:,.2f}")
    print()

    current_date += timedelta(days=1)

# =========================
# FINAL OUTPUT
# =========================

total_seconds = grand_total_ts * SECONDS_PER_TS
total_hours = total_seconds / 3600
total_days = total_hours / 24

print()
print("==========================================")
print("              FINAL TOTAL")
print("==========================================")
print(f"Date Range      : {start_date} to {end_date}")
print(f"Days Found      : {days_found:,}")
print(f"Parquet Files   : {grand_total_files:,}")
print(f"Total .TS Rows  : {grand_total_ts:,}")
print(f"Total Seconds   : {total_seconds:,.2f}")
print(f"Total Hours     : {total_hours:,.2f}")
print(f"Equivalent Days : {total_days:,.2f}")
print("==========================================")