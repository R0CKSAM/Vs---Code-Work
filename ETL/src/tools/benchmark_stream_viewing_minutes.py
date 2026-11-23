"""Compare the original and revised all-HTTP STREAM exporters over selected IST days."""
import argparse
from contextlib import redirect_stdout
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

import duckdb


EXPORTER = Path(__file__).with_name('export_stream_viewing_minutes.py').resolve()


def original_query(source):
    """Restore the original scan and join-before-grouping plan for comparison."""
    # The current exporter prepares keys during the scan. The original plan
    # materialised the raw projection as a separate table first.
    prep_start = source.index('        # Prepare the title and path keys')
    raw_start = source.index('            SELECT trim(cliIP)', prep_start)
    raw_end = source.index('\n            )\n            SELECT * EXCLUDE (raw_title)', raw_start)
    prep_end = source.index("        print('Resolving titles", raw_end)
    raw_table = ("        con.execute(f'''\n            CREATE TEMP TABLE media AS\n"
                 + source[raw_start:raw_end]
                 + "\n        ''', [start, files, start, start + 86400])\n")
    source = source[:prep_start] + raw_table + source[prep_end:]
    start = source.index("        print('Resolving titles")
    end = source.index('        stats =', start)
    metrics_start = source.index("        metrics = '''", start)
    metrics_end = source.index("'''", metrics_start + len("        metrics = '''")) + 3
    metric_definition = source[metrics_start:metrics_end]
    query = '''
        input_count, input_ts_count = con.execute(
            'SELECT count(*), count(*) FILTER (WHERE is_ts_request) FROM media'
        ).fetchone()
        con.execute(f\'''COPY (
            WITH keyed AS (
                SELECT *, {candidate} AS candidate_id,
                    CASE WHEN req_host LIKE '%vod%' OR lower(path) LIKE '%/vod/%'
                         THEN nullif(lower(split_part(ltrim(path,'/'),'/',4)), '') END AS content_key,
                    {REQUEST_TITLE_SQL} AS request_title
                FROM media
            ), titles AS (
                SELECT req_host, content_key, min(request_title) AS title
                FROM keyed WHERE content_key IS NOT NULL AND request_title IS NOT NULL
                GROUP BY ALL HAVING count(DISTINCT request_title)=1
            )
            SELECT strftime(s.minute_ist, '%d-%m-%y') AS date_ist, s.minute_ist::TIME AS time_ist,
                time_bucket(INTERVAL '15 minutes', s.minute_ist)::TIME AS bucket_start_ist,
                (time_bucket(INTERVAL '15 minutes', s.minute_ist) + INTERVAL '15 minutes')::TIME AS bucket_end_ist,
                s.cli_ip, s.req_host, s.content_key, s.candidate_id,
                coalesce(hc.host_candidate_channel_name,h.host_channel_name,p.path_channel_name,'Unmapped') AS channel,
                coalesce(s.request_title,t.title) AS content_title,
                s.country,s.state,s.city,s.asn,coalesce(a.isp,'Unknown') AS isp,
                {metrics}
            FROM keyed s
            LEFT JOIN host_candidate_map hc ON hc.reqHost=s.req_host AND hc.candidate_id=s.candidate_id
            LEFT JOIN host_map h ON h.reqHost=s.req_host
            LEFT JOIN path_map p ON p.candidate_id=s.candidate_id
            LEFT JOIN titles t USING(req_host,content_key)
            LEFT JOIN asn_lookup a ON a.asn=s.asn
            GROUP BY ALL ORDER BY date_ist,time_ist,cli_ip
        ) TO '{str(staged).replace(chr(39), chr(39)*2)}' (FORMAT PARQUET, COMPRESSION ZSTD)\''')
'''
    result = source[:start] + metric_definition + '\n' + query + source[end:]
    result = result.replace("floor((_ts - ?)/60)", "floor((try_cast(reqTimeSec AS DOUBLE)-?)/60)")
    result = result.replace("CASE WHEN queryStr ILIKE '%content_title=%'\n                     THEN nullif(regexp_extract(queryStr, '(?i)(?:^|[?&])content_title=([^&]+)', 1), '') END AS raw_title", "nullif(regexp_extract(queryStr, '(?i)(?:^|[?&])content_title=([^&]+)', 1),'') AS raw_title")
    return result.replace('FROM (SELECT *, try_cast(reqTimeSec AS DOUBLE) AS _ts\n                  FROM read_parquet(?, hive_partitioning=false))\n            WHERE _ts >= ? AND _ts < ?', 'FROM read_parquet(?, hive_partitioning=false)\n            WHERE try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--days', type=int, default=7, choices=range(1, 8), help='Number of IST days to compare.')
    args = parser.parse_args()
    current = EXPORTER.read_text(encoding='utf-8')
    namespace = {'__name__': 'bench_exporter', '__file__': str(EXPORTER)}
    exec(compile(current, str(EXPORTER), 'exec'), namespace)
    out = namespace['ARCHIVE'] / 'source=Try' / f'benchmark_{args.start}_{uuid4().hex[:8]}'
    out.mkdir(parents=True)
    print('Benchmark folder:', out, flush=True)
    cache_path = namespace['ETL'] / 'data/asn/ip2location_asn_cache.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8-sig'))
    source_by_variant = {'original': original_query(current), 'revised': current}
    for name, source in source_by_variant.items():
        variant = out / name
        variant.mkdir()
        source = source.replace("out = ARCHIVE / 'source=Try'", f'out = Path({str(variant)!r})')
        source = source.replace("cache = json.loads((ETL/'data/asn/ip2location_asn_cache.json').read_text(encoding='utf-8-sig'))", 'cache = benchmark_cache')
        source_by_variant[name] = compile(source, str(EXPORTER), 'exec')
    results = []
    for offset in range(args.days):
        day = args.start + timedelta(days=offset)
        row = {'date': str(day), 'seconds': {}, 'errors': {}}
        variants = list(source_by_variant)
        if offset % 2:
            variants.reverse()
        for name in variants:
            print(day, name, 'starting', flush=True)
            env = {'__name__': 'bench_exporter', '__file__': str(EXPORTER), 'benchmark_cache': cache}
            exec(source_by_variant[name], env)
            sys.argv = [str(EXPORTER), '--date', str(day)]
            t = perf_counter()
            with (out / f'{day}_{name}.log').open('w', encoding='utf-8') as handle, redirect_stdout(handle):
                try:
                    env['main']()
                except Exception as exc:
                    row['errors'][name] = str(exc)
            row['seconds'][name] = round(perf_counter() - t, 2)
            print(day, name, row['seconds'][name], row['errors'].get(name, 'finished'), flush=True)
        if not row['errors']:
            files = [out / name / f'stream_viewing_minutes_{day}_all_http_request_hours.parquet' for name in source_by_variant]
            with duckdb.connect() as con:
                con.execute('SET threads=4')
                row['row_count'], row['requests'] = con.execute('SELECT count(*),sum(http_requests) FROM read_parquet(?)',[str(files[0])]).fetchone()
                row['differing_rows'] = [con.execute('SELECT count(*) FROM (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM read_parquet(?))',list(map(str, pair))).fetchone()[0] for pair in (files, files[::-1])]
        results.append(row)
        (out/'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
