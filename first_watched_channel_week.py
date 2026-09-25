"""First observed STREAM playback channel per identifiable viewer, 18-24 Sep 2026 IST."""

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ETL' / 'src' / 'profile'))
from vglive_core import HOST_CANDIDATE_MAP, HOST_MAP, PATH_MAP, channel_candidate_sql
from ETL.src.live_monitor.enrichment import decoded_ua_dimensions


LAKE = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\source=stream\year=2026\month=09')
WORK = ROOT / 'ETL' / 'output' / 'temp' / 'first_watched_channel_2026_09_18_24'
OUTPUT = ROOT / 'stream_first_watched_channel_with_device_2026-09-18_to_24.csv'
IST = timezone(timedelta(hours=5, minutes=30))
START = datetime(2026, 9, 18, tzinfo=IST).timestamp()
END = datetime(2026, 9, 25, tzinfo=IST).timestamp()


def quoted(value):
    return "'" + str(value).replace('\\', '/').replace("'", "''") + "'"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET threads=4')
    con.execute("SET memory_limit='8GB'")
    con.execute(f'SET temp_directory={quoted(WORK / "duckdb_tmp")}')
    daily = []
    for day in range(17, 25):
        files = sorted((LAKE / f'day={day:02}').glob('*.parquet'))
        if not files:
            raise RuntimeError(f'Missing source partition day={day:02}')
        source = '[' + ','.join(quoted(path) for path in files) + ']'
        target = WORK / f'first_day_{day:02}.parquet'
        print(f'Processing day={day:02}, files={len(files)}', flush=True)
        con.execute(f"""
            COPY (
                WITH playback AS (
                    SELECT
                        TRY_CAST(reqTimeSec AS DOUBLE) AS event_epoch,
                        lower(COALESCE(reqHost, '')) AS host,
                        reqPath AS path,
                        cliIP AS ip,
                        nullif(regexp_extract(COALESCE(queryStr, ''), '(?i)(?:^|[?&])device_id=([^&]*)', 1), '') AS device_id,
                        nullif(regexp_extract(COALESCE(queryStr, ''), '(?i)(?:^|[?&])session_id=([^&]*)', 1), '') AS session_id,
                        nullif(trim(COALESCE(UA, '')), '') AS ua
                    FROM read_parquet({source}, union_by_name=true)
                    WHERE TRY_CAST(reqTimeSec AS DOUBLE) >= {START}
                      AND TRY_CAST(reqTimeSec AS DOUBLE) < {END}
                      AND lower(COALESCE(reqPath, '')) LIKE '%.ts'
                      AND TRY_CAST(statusCode AS DOUBLE) = 200
                ), identified AS (
                    SELECT
                        CASE WHEN device_id IS NOT NULL THEN 'device_id'
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
                SELECT identity_method, viewer_key,
                       min(event_epoch) AS first_epoch,
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
    con.register('host_map_rows', pd.DataFrame([(k, v) for k, v in HOST_MAP.items()], columns=['host', 'channel']))
    con.register('path_map_rows', pd.DataFrame([(k, v) for k, v in PATH_MAP.items()], columns=['candidate', 'channel']))
    con.register('host_candidate_rows', pd.DataFrame([(host, candidate, channel) for (host, candidate), channel in HOST_CANDIDATE_MAP.items()], columns=['host', 'candidate', 'channel']))
    candidate = channel_candidate_sql('first_path')
    query = f"""
        WITH first_event AS (
            SELECT identity_method, viewer_key,
                   min(first_epoch) AS first_epoch,
                   arg_min(first_host, first_epoch) AS first_host,
                   arg_min(first_path, first_epoch) AS first_path,
                   arg_min(first_cliIP, first_epoch) AS first_cliIP,
                   arg_min(first_ua, first_epoch) AS first_ua,
                   sum(successful_segment_requests) AS successful_segment_requests
            FROM read_parquet({source})
            GROUP BY 1,2
        ), candidate AS (
            SELECT *, {candidate} AS candidate_id FROM first_event
        )
        SELECT f.viewer_key, f.identity_method,
               strftime(to_timestamp(f.first_epoch) AT TIME ZONE 'Asia/Kolkata', '%d-%m-%Y') AS first_date_ist,
               strftime(to_timestamp(f.first_epoch) AT TIME ZONE 'Asia/Kolkata', '%H:%M:%S') AS first_time_ist,
               coalesce(hc.channel, h.channel, p.channel, 'Other') AS first_channel,
               f.first_cliIP, f.successful_segment_requests, f.first_ua
        FROM candidate f
        LEFT JOIN host_candidate_rows hc ON f.first_host = hc.host AND f.candidate_id = hc.candidate
        LEFT JOIN host_map_rows h ON f.first_host = h.host
        LEFT JOIN path_map_rows p ON f.candidate_id = p.candidate
        ORDER BY f.first_epoch, f.viewer_key
    """
    counts = {}
    decode_counts = {}
    with OUTPUT.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['viewer_key', 'identity_method', 'first_date_ist', 'first_time_ist', 'first_channel', 'first_cliIP', 'successful_segment_requests', 'device', 'device_type', 'brand', 'model', 'os', 'ua_decode_status'])
        result = con.execute(query)
        while rows := result.fetchmany(50000):
            for row in rows:
                decoded = decoded_ua_dimensions(row[7])
                device_type = decoded.get('device_type_decoded', '')
                brand = decoded.get('brand_decoded', '')
                model = decoded.get('model_decoded', '')
                os = decoded.get('os_decoded', '')
                status = decoded.get('ua_decode_status', 'Not in lookup')
                device = ' '.join(part for part in (brand, model) if part) or device_type or 'Unknown'
                writer.writerow([*row[:7], device, device_type, brand, model, os, status])
                counts[row[1]] = counts.get(row[1], 0) + 1
                decode_counts[status] = decode_counts.get(status, 0) + 1
    print(f'Rows by identity: {counts}', flush=True)
    print(f'UA decode statuses: {decode_counts}', flush=True)
    print(f'Output: {OUTPUT}', flush=True)


if __name__ == '__main__':
    main()
