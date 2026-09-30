"""Export first observed STREAM channel for 22-27 Sep 2026 in Book1 format."""

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ETL'))
sys.path.insert(0, str(ROOT / 'ETL' / 'src' / 'profile'))
from src.common.lake_partitions import discover_partitions, resolve_lake_roots
from vglive_core import DEFAULT_LAKE_FOLDER, HOST_CANDIDATE_MAP, HOST_MAP, PATH_MAP, channel_candidate_sql


IST = timezone(timedelta(hours=5, minutes=30))
START = datetime(2026, 9, 22, tzinfo=IST).timestamp()
END = datetime(2026, 9, 28, tzinfo=IST).timestamp()
WORK = ROOT / 'ETL' / 'output' / 'temp' / 'first_watched_channel_2026_09_22_27'
PRIOR_WORK = ROOT / 'ETL' / 'output' / 'temp' / 'first_watched_channel_2026_09_18_24'
OUTPUT = ROOT / 'first_watched_channel_2026-09-22_to_27.xlsx'


def quoted(value):
    return "'" + str(value).replace('\\', '/').replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-day', action='store_true', help='Include 00:00-05:59; default matches Book1 (06:00-23:59).')
    args = parser.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET threads=4')
    con.execute("SET memory_limit='8GB'")
    con.execute(f'SET temp_directory={quoted(WORK / "duckdb_tmp")}')

    daily = [PRIOR_WORK / f'first_day_{day:02}.parquet' for day in range(21, 25)]
    if any(not path.is_file() for path in daily):
        raise RuntimeError('Missing prior daily first-event files for 21-24 September')
    roots = resolve_lake_roots(DEFAULT_LAKE_FOLDER)
    parts = discover_partitions(roots, source='stream', start=date(2026, 9, 25), end=date(2026, 9, 27))
    if {part.date_text for part in parts} != {f'2026-09-{day:02}' for day in range(25, 28)}:
        raise RuntimeError('Missing source partitions for 25-27 September')

    for part in parts:
        target = WORK / f'first_day_{part.day:02}.parquet'
        source = '[' + ','.join(quoted(path) for path in part.files) + ']'
        print(f'Processing {part.date_text}: {len(part.files)} source files', flush=True)
        con.execute(f"""
            COPY (
                WITH playback AS (
                    SELECT TRY_CAST(reqTimeSec AS DOUBLE) AS event_epoch,
                           lower(coalesce(reqHost, '')) AS host, reqPath AS path,
                           cliIP AS ip,
                           nullif(regexp_extract(coalesce(queryStr, ''), '(?i)(?:^|[?&])device_id=([^&]*)', 1), '') AS device_id,
                           nullif(regexp_extract(coalesce(queryStr, ''), '(?i)(?:^|[?&])session_id=([^&]*)', 1), '') AS session_id,
                           nullif(trim(coalesce(UA, '')), '') AS ua
                    FROM read_parquet({source}, union_by_name=true)
                    WHERE TRY_CAST(reqTimeSec AS DOUBLE) >= {START}
                      AND TRY_CAST(reqTimeSec AS DOUBLE) < {END}
                      AND lower(coalesce(reqPath, '')) LIKE '%.ts'
                      AND TRY_CAST(statusCode AS DOUBLE) = 200
                ), identified AS (
                    SELECT CASE WHEN device_id IS NOT NULL THEN 'device_id'
                                WHEN session_id IS NOT NULL THEN 'session_id'
                                ELSE 'cliIP+UA' END AS identity_method,
                           CASE WHEN device_id IS NOT NULL THEN 'device:' || sha256(device_id)
                                WHEN session_id IS NOT NULL THEN 'session:' || sha256(session_id)
                                WHEN ip IS NOT NULL AND ip <> '' AND ua IS NOT NULL
                                  THEN 'ipua:' || sha256(ip || '|' || ua)
                                ELSE NULL END AS viewer_key,
                           event_epoch, host, path, ip, ua
                    FROM playback
                )
                SELECT identity_method, viewer_key, min(event_epoch) AS first_epoch,
                       arg_min(host, event_epoch) AS first_host,
                       arg_min(path, event_epoch) AS first_path,
                       arg_min(ip, event_epoch) AS first_cliIP,
                       arg_min(ua, event_epoch) AS first_ua,
                       count(*) AS successful_segment_requests
                FROM identified WHERE viewer_key IS NOT NULL
                GROUP BY identity_method, viewer_key
            ) TO {quoted(target)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        daily.append(target)

    source = '[' + ','.join(quoted(path) for path in daily) + ']'
    con.register('host_map_rows', pd.DataFrame(HOST_MAP.items(), columns=['host', 'channel']))
    con.register('path_map_rows', pd.DataFrame(PATH_MAP.items(), columns=['candidate', 'channel']))
    con.register('host_candidate_rows', pd.DataFrame([(host, candidate, channel) for (host, candidate), channel in HOST_CANDIDATE_MAP.items()], columns=['host', 'candidate', 'channel']))
    candidate = channel_candidate_sql('first_path')
    query = f"""
        WITH first_event AS (
            SELECT identity_method, viewer_key, min(first_epoch) AS first_epoch,
                   arg_min(first_host, first_epoch) AS first_host,
                   arg_min(first_path, first_epoch) AS first_path,
                   arg_min(first_cliIP, first_epoch) AS first_cliIP
            FROM read_parquet({source})
            GROUP BY 1,2
        ), candidate AS (
            SELECT *, {candidate} AS candidate_id FROM first_event
        )
        SELECT CAST(to_timestamp(f.first_epoch) AT TIME ZONE 'Asia/Kolkata' AS DATE) AS first_date_ist,
               CAST(to_timestamp(f.first_epoch) AT TIME ZONE 'Asia/Kolkata' AS TIME) AS first_time_ist,
               coalesce(hc.channel, h.channel, p.channel, 'Other') AS first_channel,
               f.first_cliIP
        FROM candidate f
        LEFT JOIN host_candidate_rows hc ON f.first_host = hc.host AND f.candidate_id = hc.candidate
        LEFT JOIN host_map_rows h ON f.first_host = h.host
        LEFT JOIN path_map_rows p ON f.candidate_id = p.candidate
        WHERE f.first_epoch >= {START} AND f.first_epoch < {END}
        {'AND hour(to_timestamp(f.first_epoch) AT TIME ZONE "Asia/Kolkata") >= 6' if not args.full_day else ''}
        ORDER BY f.first_epoch, f.viewer_key
    """.replace('"Asia/Kolkata"', "'Asia/Kolkata'")

    book = openpyxl.Workbook(write_only=True)
    sheet = book.create_sheet('Sheet1')
    sheet.append(['first_date_ist', 'first_time_ist', 'first_channel', 'first_cliIP', 'Slot'])
    counts = {}
    result = con.execute(query)
    while rows := result.fetchmany(20000):
        for day, observed_time, channel, ip in rows:
            slot = time(observed_time.hour)
            sheet.append([day, observed_time, channel, ip, slot])
            counts[str(day)] = counts.get(str(day), 0) + 1
    book.save(OUTPUT)
    print(f'Rows by date: {counts}', flush=True)
    print(f'Output: {OUTPUT}', flush=True)


if __name__ == '__main__':
    main()
