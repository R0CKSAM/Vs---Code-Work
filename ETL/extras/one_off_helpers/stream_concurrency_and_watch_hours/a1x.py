"""
VETO Stream Time Calculator
Counts .ts segment delivery rows in VETO's parquet log lake over a date
range, converts to total streaming hours, and breaks the total down by
channel using host/path/query mapping.

Usage:
    python a1x.py "Z:/Veto Logs Backup/DO NOT DELETE"

Output:
    - Console summary (daily totals + final channel breakdown)
    - channel_hours_<start>_<end>.csv written next to the script
"""

import re
import sys
import csv
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyarrow.parquet as pq
import pyarrow.compute as pc

# =========================
# CONFIG
# =========================

SECONDS_PER_TS = 6
TS_COLUMN = "reqPath"
HOST_COLUMN = "reqHost"
QUERY_COLUMN = "queryStr"
CLIENT_IP_COLUMN = "cliIP"
MAX_WORKERS = 8

# Edit this to your usual network lake root. Used when you press Enter
# at the path prompt instead of typing one.
DEFAULT_ROOT = r"Z:\Veto Logs Backup\DO NOT DELETE"

# Matches a full day-level path like:
#   ...\source=stream\year=2026\month=08\day=18
# Captures the root (everything before "source=stream") and the date.
DAY_PATH_RE = re.compile(
    r"^(?P<root>.*?)[\\/]source=stream[\\/]year=(?P<year>\d{4})"
    r"[\\/]month=(?P<month>\d{2})[\\/]day=(?P<day>\d{2})[\\/]?$",
    re.IGNORECASE,
)
# Matches a root path that already ends in "source=stream" with no date.
ROOT_WITH_SOURCE_RE = re.compile(r"^(?P<root>.*?)[\\/]source=stream[\\/]?$", re.IGNORECASE)

# =========================
# CHANNEL MAPPING
# =========================

HOST_MAP = {
    "veto-vod.akamaized.net": "Veto VOD",
    "ndtvprofit-veto.akamaized.net": "NDTV Profit",
    "ndtvprofit-veto.akamaized-staging.net": "NDTV Profit",
    "manorama-veto.akamaized.net": "Manorama",
    "b4u-veto-m.akamaized.net": "B4U Movies",
    "b4u-veto-music.akamaized.net": "B4U Music",
    "b4u-veto-kadak.akamaized.net": "B4U Kadak",
    "b4u-veto.akamaized.net": "B4U Bhojpuri",
    "vetocricket.akamaized.net": "Veto Cricket Live",
    "bmasala-live.akamaized.net": "Bollywood Masala",
}

HOST_CANDIDATE_MAP = {
    ("vetostreams.akamaized.net", "indiatv"): "India TV",
    ("vetostreams.akamaized.net:443", "indiatv"): "India TV",
    ("vetostreams.akamaized.net", "upgovlive"): "UP Government Live",
}

PATH_MAP = {
    "vglive-sk-238731": "NDTV Marathi",
    "vglive-sk-639201": "IndiaTV Cricket",
    "vglive-sk-834057": "Ndtv India",
    "vglive-sk-274906": "India TV",
    "vglive-sk-385006": "India TV Yoga",
    "vglive-sk-479089": "India TV SpeedNews",
    "vglive-sk-912213": "India TV Adalat",
    "vglive-sk-699286": "India TV Yoga",
    "vglive-sk-494434": "NDTV Rajasthan",
    "vglive-sk-618504": "NDTV Madhya Pradesh",
    "vglive-sk-722277": "NDTV 24x7",
    "speednews": "India TV SpeedNews",
    "rimo": "India TV SpeedNews",
    "yrfmusic": "YRF Music",
    "sagamusic": "SAGA Music",
    "sikhratnavali": "Sikh Ratnavali",
    "sagaharyanvi": "Saga Music Haryanvi",
    "epic_tv": "Epic TV",
    "epic_bharat": "Epic Bharat",
    "epic_bhojpuri": "Epic Bhojpuri",
    "epic_kids": "Epic Kids",
    "epic_music": "Epic Music",
    "national": "NewsNation",
    "nnup": "NewsNation UP/UK",
    "nnmp": "NewsNation MP/CH",
    "nnbrjh": "NewsNation BR/JH",
    "nnpunj": "NewsNation Punjab",
    "sanskar": "Sanskaar TV",
    "sanskaartv": "Sanskaar TV",
    "satsang": "Satsangh TV",
    "satsanghtv": "Satsangh TV",
    "shubh": "Shubh TV",
    "shubhtv": "Shubh TV",
    "9xm": "9XM",
    "9xjalwa": "9XM Jalwa",
    "9xm_jalwa": "9XM Jalwa",
    "9x_jalwa": "9XM Jalwa",
    "9xtashan": "9XM Tashan",
    "9xm_tashan": "9XM Tashan",
    "9x_tashan": "9XM Tashan",
    "9xjhakaas": "9XM Jhakaas",
    "9xm_jhakaas": "9XM Jhakaas",
    "9x_jhakaas": "9XM Jhakaas",
    "gtcnews": "GTC News",
    "gtc_news": "GTC News",
    "gtcpunjabi": "GTC Punjabi",
    "gtc_punjabi": "GTC Punjabi",
    "punjabshort": "Punjabi Shorts",
    "punjabi_shorts": "Punjabi Shorts",
    "b4umo001": "B4U Movies",
    "b4um001": "B4U Music",
    "b4ua001": "B4U Kadak",
    "b4u_bhojpuri": "B4U Bhojpuri",
    "bollywoodmasala": "Bollywood Masala",
    "vetocricketlive": "Veto Cricket Live",
}

QUERY_CHANNEL_ALIASES = {
    "speednews": "India TV SpeedNews",
    "yogatv": "India TV Yoga",
    "aapkiadalat": "India TV Adalat",
}

VGLIVE_RE = re.compile(r"(vglive-sk-\d+)", re.IGNORECASE)


def resolve_channel(host, path, query):
    """
    Resolution order:
      1. Exact reqHost match (HOST_MAP)
      2. vglive-sk-NNNNN id found anywhere in the path (PATH_MAP)
      3. (host, keyword-in-path) candidate pairs (HOST_CANDIDATE_MAP)
      4. Any '/'-separated path segment matching a PATH_MAP key
      5. queryStr alias match (QUERY_CHANNEL_ALIASES)
      6. "Unmapped" — kept as its own bucket so nothing is silently dropped
    """
    host_l = (host or "").lower()
    path_l = (path or "").lower()

    if host_l in HOST_MAP:
        return HOST_MAP[host_l]

    m = VGLIVE_RE.search(path_l)
    if m and m.group(1) in PATH_MAP:
        return PATH_MAP[m.group(1)]

    for (h, kw), ch in HOST_CANDIDATE_MAP.items():
        if h.lower() == host_l and kw.lower() in path_l:
            return ch

    for seg in re.split(r"[\\/]", path_l):
        if seg in PATH_MAP:
            return PATH_MAP[seg]

    if query:
        q_l = query.lower()
        for k, ch in QUERY_CHANNEL_ALIASES.items():
            if k in q_l:
                return ch

    return "Unmapped"


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


def get_root_path():
    """
    Accepts either:
      - the bare lake root (e.g. Z:\\Veto Logs Backup\\DO NOT DELETE)
      - a root that already ends in source=stream
      - a full day-level path (...\\source=stream\\year=YYYY\\month=MM\\day=DD),
        e.g. pasted straight from a local ETL output folder
    Source: a CLI argument if one was passed, otherwise an interactive
    prompt (Enter for DEFAULT_ROOT).
    Returns (root_path, detected_date_or_None).
    """
    if len(sys.argv) >= 2:
        raw = sys.argv[1]
    else:
        print(f"Default path: {DEFAULT_ROOT}")
        raw = input("Lake root or day-folder path (Enter for default): ").strip()
        if not raw:
            raw = DEFAULT_ROOT

    raw = raw.strip('"').rstrip("\\/")

    m = DAY_PATH_RE.match(raw)
    if m:
        detected_date = datetime(
            int(m.group("year")), int(m.group("month")), int(m.group("day"))
        ).date()
        return Path(m.group("root")), detected_date

    m = ROOT_WITH_SOURCE_RE.match(raw)
    if m:
        return Path(m.group("root")), None

    return Path(raw), None


def count_ts_by_channel(file):
    """
    Reads only the columns needed (path/host/query/cliIP), filters to
    .ts rows with vectorized Arrow ops, then resolves each surviving row
    to a channel. Returns:
      - channel_counts: Counter of channel -> .ts row count
      - channel_ips:    dict of channel -> set of distinct cliIP values
    """
    try:
        table = pq.read_table(
            file, columns=[TS_COLUMN, HOST_COLUMN, QUERY_COLUMN, CLIENT_IP_COLUMN]
        )
    except Exception as e:
        print(f"  ERROR reading {file.name}: {e}")
        return Counter(), {}

    path_col = table.column(TS_COLUMN)
    mask = pc.ends_with(path_col, ".ts")

    paths = pc.filter(path_col, mask).to_pylist()
    hosts = pc.filter(table.column(HOST_COLUMN), mask).to_pylist()
    queries = pc.filter(table.column(QUERY_COLUMN), mask).to_pylist()
    ips = pc.filter(table.column(CLIENT_IP_COLUMN), mask).to_pylist()

    counts = Counter()
    channel_ips = defaultdict(set)
    for h, p, q, ip in zip(hosts, paths, queries, ips):
        channel = resolve_channel(h, p, q)
        counts[channel] += 1
        if ip:
            channel_ips[channel].add(ip)
    return counts, channel_ips


def process_day(parquet_files):
    day_counts = Counter()
    day_ips = defaultdict(set)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(count_ts_by_channel, f): f for f in parquet_files}
        for fut in as_completed(futures):
            file_counts, file_ips = fut.result()
            day_counts.update(file_counts)
            for channel, ip_set in file_ips.items():
                day_ips[channel] |= ip_set
    return day_counts, day_ips


# =========================
# MAIN
# =========================

def main():
    root, detected_date = get_root_path()

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

    if detected_date:
        print(f"Detected date in pasted path: {detected_date}")
        use_detected = input("Use this as the single day to process? [Y/n]: ").strip().lower()
        if use_detected in ("", "y", "yes"):
            start_date = end_date = detected_date
        else:
            start_date = get_date("Start Date (YYYY-MM-DD): ")
            end_date = get_date("End Date   (YYYY-MM-DD): ")
    else:
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
    grand_total_files = 0
    days_found = 0
    grand_channel_counts = Counter()
    grand_channel_ips = defaultdict(set)

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

        day_counts, day_ips = process_day(parquet_files)
        grand_channel_counts.update(day_counts)
        for channel, ip_set in day_ips.items():
            grand_channel_ips[channel] |= ip_set

        day_ts = sum(day_counts.values())
        day_hours = (day_ts * SECONDS_PER_TS) / 3600
        day_distinct_ips = len(set().union(*day_ips.values())) if day_ips else 0

        print(f"  Files       : {len(parquet_files):,}")
        print(f"  .TS Rows    : {day_ts:,}")
        print(f"  Hours       : {day_hours:,.2f}")
        print(f"  Distinct IPs: {day_distinct_ips:,}")
        print()

        current_date += timedelta(days=1)

    # =========================
    # FINAL OUTPUT
    # =========================

    grand_total_ts = sum(grand_channel_counts.values())
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

    print()
    print("==========================================")
    print("        CHANNEL-WISE WATCH HOURS")
    print("==========================================")
    rows_sorted = sorted(grand_channel_counts.items(), key=lambda kv: kv[1], reverse=True)
    csv_rows = []
    for channel, rows in rows_sorted:
        hours = (rows * SECONDS_PER_TS) / 3600
        pct = (rows / grand_total_ts * 100) if grand_total_ts else 0
        distinct_ips = len(grand_channel_ips.get(channel, ()))
        print(f"  {channel:28s} {hours:>12,.2f} hrs  ({pct:5.2f}%)  {distinct_ips:>8,} distinct IPs")
        csv_rows.append([channel, rows, round(hours, 2), round(pct, 2), distinct_ips])
    print("==========================================")

    overall_distinct_ips = (
        len(set().union(*grand_channel_ips.values())) if grand_channel_ips else 0
    )
    print(f"Overall distinct client IPs (any channel): {overall_distinct_ips:,}")

    csv_prompt = input(
        "Save channel breakdown as CSV? [y/N] (or enter a folder/file path to save there): "
    ).strip()

    if csv_prompt:
        default_name = f"channel_hours_{start_date}_{end_date}.csv"
        lowered = csv_prompt.lower()

        if lowered in ("y", "yes"):
            csv_path = Path(default_name)
        elif lowered in ("n", "no"):
            csv_path = None
        else:
            # Treat as a path: a directory gets the default filename
            # appended; anything else is used as the exact file path.
            given = Path(csv_prompt.strip('"'))
            csv_path = (given / default_name) if given.is_dir() else given

        if csv_path:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["channel", "ts_rows", "hours", "pct_of_total", "distinct_client_ips"]
                )
                writer.writerows(csv_rows)
            print()
            print(f"Channel breakdown saved to: {csv_path.resolve()}")
        else:
            print("Skipped saving CSV.")
    else:
        print("Skipped saving CSV.")


if __name__ == "__main__":
    main()