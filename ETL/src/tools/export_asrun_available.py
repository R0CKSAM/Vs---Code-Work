"""Export available Spot/L-band delivery using the dashboard CSV column contract."""

import argparse
import csv
from datetime import timedelta
import json
from pathlib import Path
import re
import shutil

import duckdb
import pandas as pd

ETL = Path(__file__).resolve().parents[2]


def is_main_india_tv(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower()) == "indiatv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--main-india-tv-only", action="store_true")
    args = parser.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with args.reference.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    parsed = ETL / "asrun_demo/data/parsed"
    archive = Path(r"Z:\Veto Logs Backup\DO NOT DELETE\source=AsRUN")
    paths = [archive / f"ASRUN-{d:%d%m%y}.txt" for d in pd.date_range(start, end)]
    # The parsed cache already includes the verified 12-18 October source files.
    # Use this completed local artifact without waiting on the busy network share.
    events = pd.read_parquet(parsed / "asrun_events.parquet")
    known_files = set(events.source_file)
    missing_files = [p.name for p in paths if p.name not in known_files]
    events = events.loc[events.is_ad & events.ad_type.isin(["Spot", "L-band"])
                        & events.on_air_start_ist.ge(start)
                        & events.on_air_start_ist.lt(end + timedelta(days=1))].copy()
    events = events.sort_values(["on_air_start_ist", "source_file", "source_line"])
    snapshot = args.output_dir / "identity_snapshot.parquet"
    shutil.copy2(args.identity, snapshot)
    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='1GB'")

    def load(name, path, time_column):
        con.read_parquet(str(path)).create_view(name)
        return con.execute(f"SELECT * FROM {name} WHERE CAST({time_column} AS TIMESTAMP) >= ? "
                           f"AND CAST({time_column} AS TIMESTAMP) < ?", [start, end + timedelta(days=1)]).df()

    # Aggregate minute sums before loading into Python to keep memory bounded.
    con.read_parquet(str(snapshot)).create_view("identity_all")
    channel_filter = (" WHERE regexp_replace(lower(channel_name), '[^a-z0-9]', '', 'g') = 'indiatv'"
                      if args.main_india_tv_only else "")
    con.execute("CREATE TEMP VIEW identity_data AS SELECT * FROM identity_all" + channel_filter)
    viewer = con.execute(
        "SELECT source,time_bucket(INTERVAL '5 minutes',CAST(minute_ist AS TIMESTAMP)) bucket, "
        "sum(distinct_cliips) total FROM identity_data WHERE log_date BETWEEN ? AND ? GROUP BY 1,2",
        [args.start, args.end]).df()
    dims = con.execute("SELECT DISTINCT source,platform_name,channel_name FROM identity_data "
                       "WHERE log_date BETWEEN ? AND ?", [args.start, args.end]).df()
    amagi = load("amagi", parsed / "amagi_minute.parquet", "minute_ist")
    if args.main_india_tv_only:
        amagi = amagi.loc[amagi.channel_name.map(is_main_india_tv)].copy()
    videos = load("videos", parsed / "youtube_video_minute.parquet", "timestamp_ist")
    collector = load("collector", parsed / "youtube_collector_minute.parquet", "timestamp_ist")
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", str(value).lower())
    videos = videos.loc[videos.youtube_channel.map(normalize).eq("indiatv")]
    collector = collector.loc[collector.youtube_channel.map(normalize).eq("indiatv")]
    maps = {s: dict(zip(g.bucket, g.total)) for s, g in viewer.groupby("source")}
    amagi["bucket"] = amagi.minute_ist.dt.floor("5min")
    maps["amagi"] = amagi.groupby("bucket", observed=True).concurrent_viewers.sum().to_dict()
    video_groups = {t: g for t, g in videos.groupby("timestamp_ist")}
    statuses = {t: {part.strip().lower() for status in g.collector_status for part in str(status).split("|") if part.strip()}
                for t, g in collector.groupby("timestamp_ist")}
    collector_dates = set(collector.log_date)
    join_values = lambda values: " | ".join(sorted(set(str(v) for v in values if pd.notna(v))))
    selections = [join_values(dims.loc[dims.source.eq("fast"), "platform_name"]),
                  join_values(dims.loc[dims.source.eq("fast"), "channel_name"]),
                  join_values(dims.loc[dims.source.eq("stream"), "channel_name"]),
                  join_values(amagi.platform_name), join_values(amagi.channel_name)]
    creative_selection = " || ".join(f"{t}: " + join_values(events.loc[events.ad_type.eq(t), "creative_title"])
                                     for t in ("Spot", "L-band"))
    rows = []
    for event in events.itertuples():
        timestamp = event.on_air_start_ist
        bucket, minute = timestamp.floor("5min"), timestamp.floor("min")
        audience = [maps.get(s, {}).get(bucket) for s in ("fast", "stream", "amagi")]
        yt, ids, titles, count = None, "", "", 0
        if minute in video_groups:
            group = video_groups[minute]
            yt = group.concurrent_viewers.sum()
            ids, titles = join_values(group.video_id), join_values(group.title)
            count, scope = group.video_id.nunique(), "India TV"
        elif "lookup_error" in statuses.get(minute, set()):
            scope = "India TV YouTube collector lookup error"
        elif statuses.get(minute):
            yt, scope = 0, "India TV YouTube observed; no live stream"
        else:
            scope = ("Missing India TV YouTube collector minute" if str(timestamp.date()) in collector_dates
                     else "No India TV YouTube collection for date")
        all_values = audience + [yt]
        missing = [name for name, value in zip(("FAST", "STREAM", "AMAGI", "YouTube"), all_values) if value is None]
        window = bucket.strftime("%I:%M %p") + "-" + (bucket + timedelta(minutes=4)).strftime("%I:%M %p") + " IST"
        values = [args.start, args.end, "Spot | L-band", "Spot: All Spot ad IDs || L-band: All L-band ad IDs",
                  creative_selection, timestamp.strftime("%d-%m-%y %I:%M:%S %p"),
                  event.status if pd.notna(event.status) else "", event.source_file, event.source_line,
                  event.ad_type, event.event_id, event.creative_title, event.actual_duration_seconds,
                  window, *selections, "India TV", *audience, scope, yt, count, ids, titles,
                  None if missing else sum(all_values),
                  "Missing source data: " + ", ".join(missing) if missing else "All sources covered",
                  "FAST / STREAM / AMAGI: sum of five one-minute concurrency samples; YouTube: exact event minute"]
        assert len(values) == len(header)
        rows.append([int(v) if isinstance(v, (float, int)) and pd.notna(v) and float(v).is_integer() else v for v in values])
    suffix = "_india_tv_only" if args.main_india_tv_only else ""
    filename = f"asrun_all_delivered_events_spot_l_band_{args.start}_to_{args.end}{suffix}.csv"
    destination = args.output_dir / filename
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    exported = pd.DataFrame(rows, columns=header)
    # Compare existing October 14 audience values with the user's actual UI export.
    reference = pd.read_csv(args.reference)
    key = ["ASRUN Source File", "ASRUN Source Line", "Ad ID"]
    metrics = ["FAST 5-Minute Concurrency", "STREAM 5-Minute Concurrency", "AMAGI 5-Minute Actual Concurrency"]
    joined = reference.merge(exported, on=key, suffixes=("_reference", "_export"), validate="one_to_one")
    mismatches = {m: int((pd.to_numeric(joined[m+"_reference"], errors="coerce").fillna(-1)
                         != pd.to_numeric(joined[m+"_export"], errors="coerce").fillna(-1)).sum()) for m in metrics}
    audit = dict(file=str(destination), rows=len(rows), rows_by_date=events.groupby("on_air_date").size().to_dict(),
                 missing_source_files=missing_files, reference_matched_rows=len(joined),
                 reference_metric_mismatches=mismatches,
                 coverage_counts=exported["Coverage Status"].value_counts().to_dict(),
                 identity_source=str(args.identity),
                 channel_scope="Main India TV only" if args.main_india_tv_only else "All channels",
                 selected_channels=dict(zip(["FAST platforms", "FAST channels", "STREAM channels", "AMAGI platforms", "AMAGI channels"], selections)))
    if args.main_india_tv_only:
        audit["reference_metric_mismatches"] = None
        audit["reference_comparison_note"] = "Schema matched; audience totals intentionally differ from the all-channel sample."
    (args.output_dir / "export_validation.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    con.close()


if __name__ == "__main__":
    main()
