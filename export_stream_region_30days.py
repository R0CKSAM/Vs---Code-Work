"""Export STREAM region watch hours and exact period-wide distinct client IPs."""

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ETL'))
sys.path.insert(0, str(ROOT / 'ETL' / 'src' / 'profile'))
from src.common.lake_partitions import discover_partitions, resolve_lake_roots
from vglive_core import CHUNK_DURATION_HOURS, DEFAULT_LAKE_FOLDER

START_DATE = date(2026, 8, 29)
END_DATE = date(2026, 9, 27)
IST = timezone(timedelta(hours=5, minutes=30))
START_EPOCH = datetime.combine(START_DATE, datetime.min.time(), IST).timestamp()
END_EPOCH = datetime.combine(END_DATE + timedelta(days=1), datetime.min.time(), IST).timestamp()
WORK = ROOT / 'ETL' / 'output' / 'temp' / 'stream_region_20260829_20260927'
OUTPUT = ROOT / 'ETL' / 'output' / 'exports' / 'stream_region_watch_hours_2026-08-29_to_2026-09-27.csv'


def sql_text(value):
    return "'" + str(value).replace('\\', '/').replace("'", "''") + "'"


def main():
    roots = resolve_lake_roots(DEFAULT_LAKE_FOLDER)
    partitions = discover_partitions(roots, source='stream', start=START_DATE, end=END_DATE)
    available = {partition.date_text for partition in partitions}
    expected = {(START_DATE + timedelta(days=day)).isoformat() for day in range(30)}
    missing = sorted(expected - available)
    if missing:
        raise RuntimeError(f'Missing STREAM dates: {missing}')
    WORK.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET threads=4')
    con.execute("SET memory_limit='8GB'")
    con.execute(f'SET temp_directory={sql_text(WORK / "duckdb_tmp")}')
    files = []
    for index, partition in enumerate(partitions, 1):
        source = '[' + ','.join(sql_text(path) for path in partition.files) + ']'
        target = WORK / f'ip_region_{partition.date_text}.parquet'
        if '--finalize-only' in sys.argv:
            if not target.is_file():
                raise RuntimeError(f'Missing intermediate: {target}')
            files.append(target)
            continue
        print(f'[{index}/{len(partitions)}] {partition.date_text}, files={len(partition.files)}', flush=True)
        con.execute(f"""
            COPY (
                SELECT
                    coalesce(nullif(trim(coalesce(try(url_decode(country)), country)), ''), 'Unknown') AS country,
                    coalesce(nullif(trim(coalesce(try(url_decode(state)), state)), ''), 'Unknown') AS region,
                    nullif(trim(cliIP), '') AS cliIP,
                    count(*) AS segment_requests,
                    count(*) FILTER (WHERE TRY_CAST(statusCode AS DOUBLE)=200) AS successful_segment_requests
                FROM read_parquet({source}, union_by_name=true)
                WHERE lower(coalesce(reqPath, '')) LIKE '%.ts'
                  AND TRY_CAST(reqTimeSec AS DOUBLE)>={START_EPOCH}
                  AND TRY_CAST(reqTimeSec AS DOUBLE)<{END_EPOCH}
                GROUP BY 1,2,3
            ) TO {sql_text(target)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        files.append(target)
    source = '[' + ','.join(sql_text(path) for path in files) + ']'
    query = f"""
        SELECT country, region,
               round(sum(segment_requests)*{CHUNK_DURATION_HOURS}, 3) AS raw_watch_hours,
               count(DISTINCT cliIP) AS distinct_cliIP
        FROM read_parquet({source})
        GROUP BY 1,2
        ORDER BY raw_watch_hours DESC, country, region
    """
    rows = con.execute(query).fetchall()
    with OUTPUT.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['country', 'region', 'raw_watch_hours', 'distinct_cliIP'])
        writer.writerows(rows)
    global_counts = con.execute(f"""
        SELECT sum(segment_requests), sum(successful_segment_requests), count(DISTINCT cliIP)
        FROM read_parquet({source})
    """).fetchone()
    metadata = {
        'start_ist': START_DATE.isoformat(), 'end_ist': END_DATE.isoformat(),
        'reporting_days': len(available), 'source': 'stream', 'region_field': 'state',
        'segment_duration_seconds_assumed': CHUNK_DURATION_HOURS * 3600,
        'watch_hours_basis': 'raw watch hours: all .ts requests, with no HTTP status filter',
        'distinct_cliIP_basis': 'exact distinct nonblank IP over the full period within each country/region',
        'segment_requests': global_counts[0], 'successful_segment_requests': global_counts[1],
        'global_distinct_cliIP': global_counts[2], 'region_rows': len(rows),
        'lake_roots': [str(root) for root in roots],
    }
    OUTPUT.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata), flush=True)
    print(OUTPUT, flush=True)


if __name__ == '__main__':
    main()
