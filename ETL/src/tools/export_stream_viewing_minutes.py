"""Export STREAM requests and dashboard-style TS request seconds by IP and IST minute."""
import argparse
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

ETL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ETL / 'src/profile'))
from vglive_deep_profile import channel_candidate_sql, register_maps, url_decode_text_sql

IST = ZoneInfo('Asia/Kolkata')
ARCHIVE = Path(r'Z:\Veto Logs Backup\DO NOT DELETE')

METRIC_COLS = 'http_requests, estimated_watch_seconds'
REQUEST_TITLE_SQL = url_decode_text_sql("replace(raw_title, '+', ' ')")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat, default=datetime.now(IST).date()-timedelta(days=1))
    parser.add_argument('--all-http', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    day = args.date
    inputs = sorted((ARCHIVE / 'source=stream' / f'year={day:%Y}' / f'month={day:%m}' / f'day={day:%d}').glob('part_*.parquet'))
    if not inputs:
        raise FileNotFoundError(f'No archived STREAM input for {day}')
    files = list(map(str, inputs))
    out = ARCHIVE / 'source=Try'
    out.mkdir(exist_ok=True)
    final = out / f'stream_viewing_minutes_{day}_all_http_request_hours.parquet'
    if final.exists():
        raise FileExistsError(final)
    staged = out / f'.{final.stem}_{uuid4().hex}.partial'
    start = datetime.combine(day, time.min, IST).timestamp()
    cache = json.loads((ETL/'data/asn/ip2location_asn_cache.json').read_text(encoding='utf-8-sig'))
    asns = pd.DataFrame([(str(k), v.get('as_name')) for k, v in cache.items() if v.get('status') == 'ok'], columns=['asn', 'isp'])
    with ExitStack() as cleanup, TemporaryDirectory(prefix='.duckdb_scratch_', dir=out) as scratch, duckdb.connect(
        config={'threads': 6, 'memory_limit': '8GB', 'temp_directory': scratch}
    ) as con:
        cleanup.callback(staged.unlink, missing_ok=True)
        register_maps(con)
        con.register('asn_lookup', asns)
        print(f'Scanning {len(inputs)} archived STREAM files for {day}', flush=True)
        candidate = channel_candidate_sql('path')
        geography = ', '.join(f'{url_decode_text_sql(c)} AS {c}' for c in ('country', 'state', 'city'))

        # Prepare the title and path keys during the lake scan. Both later queries reuse keyed.
        con.execute(f'''
            CREATE TEMP TABLE keyed AS
            WITH media AS (
            SELECT trim(cliIP) AS cli_ip, lower(trim(reqHost)) AS req_host,
                split_part(reqPath, '?', 1) AS path,
                reqPath LIKE '%.ts' AS is_ts_request,
                TIMESTAMP '{day} 00:00:00' + floor((_ts - ?)/60)::BIGINT * INTERVAL '1 minute' AS minute_ist,
                {geography}, regexp_replace(upper(trim(asn)), '^AS', '') AS asn,
                CASE WHEN queryStr ILIKE '%content_title=%'
                     THEN nullif(regexp_extract(queryStr, '(?i)(?:^|[?&])content_title=([^&]+)', 1), '') END AS raw_title
            FROM (SELECT *, try_cast(reqTimeSec AS DOUBLE) AS _ts
                  FROM read_parquet(?, hive_partitioning=false))
            WHERE _ts >= ? AND _ts < ?
            )
            SELECT * EXCLUDE (raw_title), {candidate} AS candidate_id,
                CASE WHEN req_host LIKE '%vod%' OR lower(path) LIKE '%/vod/%'
                     THEN nullif(lower(split_part(ltrim(path,'/'),'/',4)), '') END AS content_key,
                {REQUEST_TITLE_SQL} AS request_title
            FROM media
        ''', [start, files, start, start + 86400])
        print('Resolving titles and channels, then aggregating segments', flush=True)
        input_count, input_ts_count = con.execute(
            'SELECT count(*), count(*) FILTER (WHERE is_ts_request) FROM keyed'
        ).fetchone()

        con.execute('''
            CREATE TEMP TABLE titles AS
            SELECT req_host, content_key, min(request_title) AS title
            FROM keyed WHERE content_key IS NOT NULL AND request_title IS NOT NULL
            GROUP BY ALL HAVING count(DISTINCT request_title) = 1
        ''')

        # 3. Aggregate with a narrower key: channel and ISP are joined afterwards, since they are
        #    fully determined by (req_host, candidate_id) and asn, which are already in the key.
        # Match the dashboard: credit every raw .ts request, including repeated paths.
        metrics = '''count(*) AS http_requests,
            6 * (count(*) FILTER (WHERE s.is_ts_request)) AS estimated_watch_seconds'''
        con.execute(f'''
            CREATE TEMP TABLE agg AS
            SELECT s.minute_ist, s.cli_ip, s.req_host, s.content_key, s.candidate_id,
                coalesce(s.request_title, t.title) AS content_title,
                s.country, s.state, s.city, s.asn,
                {metrics}
            FROM keyed s
            LEFT JOIN titles t USING(req_host, content_key)
            GROUP BY ALL
        ''')
        con.execute('DROP TABLE keyed')

        # 4. Join channel and ISP labels on the aggregated rows.
        con.execute(f'''
          COPY (
            SELECT strftime(a.minute_ist, '%d-%m-%y') AS date_ist, a.minute_ist::TIME AS time_ist,
                time_bucket(INTERVAL '15 minutes', a.minute_ist)::TIME AS bucket_start_ist,
                (time_bucket(INTERVAL '15 minutes', a.minute_ist) + INTERVAL '15 minutes')::TIME AS bucket_end_ist,
                a.cli_ip, a.req_host, a.content_key, a.candidate_id,
                coalesce(hc.host_candidate_channel_name, h.host_channel_name, p.path_channel_name, 'Unmapped') AS channel,
                a.content_title, a.country, a.state, a.city, a.asn,
                coalesce(i.isp, 'Unknown') AS isp,
                {METRIC_COLS}
            FROM agg a
            LEFT JOIN host_candidate_map hc ON hc.reqHost=a.req_host AND hc.candidate_id=a.candidate_id
            LEFT JOIN host_map h ON h.reqHost=a.req_host
            LEFT JOIN path_map p ON p.candidate_id=a.candidate_id
            LEFT JOIN asn_lookup i ON i.asn=a.asn
            ORDER BY a.minute_ist, a.cli_ip
          ) TO '{str(staged).replace(chr(39), chr(39)*2)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        ''')

        stats = con.execute('''WITH checked AS (
                    SELECT *, strptime(date_ist, '%d-%m-%y')::DATE + time_ist AS minute_ist,
                           time_bucket(INTERVAL '15 minutes', minute_ist) AS expected_bucket
                    FROM read_parquet(?, hive_partitioning=false))
                    SELECT count(*), count(DISTINCT cli_ip), sum(http_requests), sum(estimated_watch_seconds),
                    min(minute_ist), max(minute_ist), count(*) FILTER(WHERE content_title IS NOT NULL),
                    count(*) FILTER(WHERE isp = 'Unknown'),
                    count(*) FILTER(WHERE estimated_watch_seconds > 60), max(estimated_watch_seconds),
                    count(*) FILTER(WHERE bucket_start_ist IS DISTINCT FROM expected_bucket::TIME
                        OR bucket_end_ist IS DISTINCT FROM (expected_bucket + INTERVAL '15 minutes')::TIME)
                    FROM checked''', [str(staged)]).fetchone()
        rows, ips, request_total, seconds, first, last, titled, unknown_isp, over_minute, max_seconds, bad_buckets = stats
        if not rows or bad_buckets:
            raise RuntimeError(f'Invalid export: {rows} rows, {bad_buckets} invalid buckets')
        if request_total != input_count:
            raise RuntimeError(f'HTTP request count mismatch: {request_total} vs {input_count}')
        if seconds != 6 * input_ts_count:
            raise RuntimeError(f'TS request seconds mismatch: {seconds} vs {6 * input_ts_count}')

        # Count from the Parquet footers and scan timestamps only when rows were excluded.
        (raw_total,) = con.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)', [files]).fetchone()
        skipped = raw_total - input_count
        if skipped:
            invalid_time, outside_day = con.execute('''
                SELECT count(*) FILTER (WHERE ts IS NULL OR NOT isfinite(ts)),
                       count(*) FILTER (WHERE isfinite(ts) AND (ts < ? OR ts >= ?))
                FROM (SELECT try_cast(reqTimeSec AS DOUBLE) AS ts
                      FROM read_parquet(?, hive_partitioning=false))
            ''', [start, start + 86400, files]).fetchone()
            if skipped != invalid_time + outside_day:
                raise RuntimeError(f'STREAM input row accounting mismatch: {raw_total:,} raw, {input_count:,} kept')
            print(f'Skipped {skipped:,} rows ({invalid_time:,} invalid timestamps, {outside_day:,} outside IST date)', flush=True)
        print(f'Raw requests: {raw_total:,}; kept: {input_count:,}', flush=True)
        print(f'HTTP requests across all statuses: {request_total:,}', flush=True)
        print(f'TS requests including repeated paths: {input_ts_count:,}', flush=True)
        print(f'Unknown ISP: {unknown_isp:,}/{rows:,} rows; rows above 60 request seconds: {over_minute:,} (max {max_seconds:,})', flush=True)
        if unknown_isp == rows:
            print('Warning: no exported rows have a decoded ISP', flush=True)
        staged.rename(final)
    print(f'{rows:,} rows, {ips:,} client IPs, {seconds:,} estimated seconds, {titled:,} titled rows; {first} to {last} IST', flush=True)
    print(final, flush=True)


if __name__ == '__main__':
    main()
