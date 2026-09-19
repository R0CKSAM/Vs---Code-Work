"""Read-only raw spool versus lake audit, with explicit UTC/IST boundaries."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import os
from pathlib import Path
import sys

import duckdb
import orjson

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'ETL/src/tools'))
from build_concurrency import DEFAULT_LAKE_FOLDER, configure_lake_selection, parquet_source_sql

START = 1789583400
END = START + 86400


def empty():
    return {'rows': 0, 'ts_rows': 0, 'ips': set(), 'ts_ips': set()}


def add(result, ip, segment):
    result['rows'] += 1
    result['ts_rows'] += int(segment)
    if ip is not None and str(ip).strip() not in ('', '-'):
        result['ips'].add(str(ip).strip())
        if segment:
            result['ts_ips'].add(str(ip).strip())


def merge(target, other):
    for key in ('rows', 'ts_rows'):
        target[key] += other[key]
    for key in ('ips', 'ts_ips'):
        target[key].update(other[key])


def scan_batch(paths):
    all_rows, ist = empty(), empty()
    errors = {'read_errors': 0, 'parse_errors': 0, 'invalid_timestamps': 0}
    for path in paths:
        try:
            with gzip.open(path, 'rb') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        row = orjson.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError('Not an object')
                    except (ValueError, orjson.JSONDecodeError):
                        errors['parse_errors'] += 1
                        continue
                    segment = str(row.get('reqPath') or '').lower().endswith('.ts')
                    add(all_rows, row.get('cliIP'), segment)
                    try:
                        timestamp = float(row.get('reqTimeSec'))
                    except (TypeError, ValueError):
                        errors['invalid_timestamps'] += 1
                        continue
                    if START <= timestamp < END:
                        add(ist, row.get('cliIP'), segment)
        except (OSError, EOFError):
            errors['read_errors'] += 1
    return all_rows, ist, errors


def summary(value):
    return {key: len(item) if isinstance(item, set) else item for key, item in value.items()}


def lake_scan(con, files, where='TRUE'):
    reader = f'read_parquet({parquet_source_sql(files)}, union_by_name=true)'
    result = empty()
    result['rows'], result['ts_rows'] = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE lower(reqPath) LIKE '%.ts')
        FROM {reader} WHERE {where}""").fetchone()
    for ip, has_ts in con.execute(f"""
        SELECT trim(cliIP), bool_or(lower(reqPath) LIKE '%.ts')
        FROM {reader} WHERE ({where}) AND cliIP IS NOT NULL
        AND trim(cliIP) NOT IN ('','-') GROUP BY 1""").fetchall():
        result['ips'].add(ip)
        if has_ts:
            result['ts_ips'].add(ip)
    return result


def compare(raw, lake):
    return {'raw': summary(raw), 'lake': summary(lake),
            'raw_minus_lake_rows': raw['rows'] - lake['rows'],
            'raw_minus_lake_ts_rows': raw['ts_rows'] - lake['ts_rows'],
            'missing_cliips_in_lake': len(raw['ips'] - lake['ips']),
            'extra_cliips_in_lake': len(lake['ips'] - raw['ips']),
            'missing_ts_cliips_in_lake': len(raw['ts_ips'] - lake['ts_ips']),
            'extra_ts_cliips_in_lake': len(lake['ts_ips'] - raw['ts_ips'])}


def main():
    output = ROOT / 'ETL/output/validation/stream_sep17_cliip_audit.json'
    report = {'date': '2026-09-17', 'source': 'stream', 'raw_folders': {}}
    source17, ist = empty(), empty()
    for day in (17, 16):
        folder = ROOT / f'ETL/data/live_spool/09-{day}-2026'
        entries = [e for e in os.scandir(folder) if e.name.endswith('.gz')]
        files = sorted(e.path for e in entries)
        info = {'files': len(files), 'bytes': sum(e.stat().st_size for e in entries),
                'read_errors': 0, 'parse_errors': 0, 'invalid_timestamps': 0}
        del entries
        print(f'Inventory {day}: {info}', flush=True)
        if not files:
            raise RuntimeError(f'No raw files in {folder}')
        batches = [files[i:i+1000] for i in range(0, len(files), 1000)]
        total = empty()
        with ProcessPoolExecutor(max_workers=12) as pool:
            for n, (all_rows, day_rows, errors) in enumerate(pool.map(scan_batch, batches), 1):
                merge(total, all_rows)
                merge(ist, day_rows)
                for key, value in errors.items():
                    info[key] += value
                if n % 5 == 0:
                    print(f'RAW {day}: {min(n*1000,len(files))}/{len(files)} files', flush=True)
        info.update(summary(total))
        report['raw_folders'][str(day)] = info
        if day == 17:
            source17 = total
        print(f'RAW {day} done: {info}', flush=True)
    args = argparse.Namespace(start='2026-09-17', end='2026-09-18', source='stream',
                              lake=DEFAULT_LAKE_FOLDER, archive_lake=[])
    configure_lake_selection(args)
    files = [f for p in args.selected_partitions for f in p.files
             if Path(f).name.startswith('part_stream_2026_09_17_')]
    dayfiles = [f for p in args.selected_partitions if p.date_text == '2026-09-17' for f in p.files]
    if not files or not dayfiles:
        raise RuntimeError('Missing required lake files')
    con = duckdb.connect()
    con.execute('SET threads=2')
    con.execute("SET memory_limit='2GB'")
    report['source_folder_17'] = compare(source17, lake_scan(con, files))
    report['ist_day_17'] = compare(ist, lake_scan(con, dayfiles,
        f'try_cast(reqTimeSec as double)>={START} AND try_cast(reqTimeSec as double)<{END}'))
    report['lake_source_files'] = [str(f) for f in files]
    report['lake_ist_files'] = [str(f) for f in dayfiles]
    report['note'] = 'Raw includes duplicates; lake is deduplicated. IP sets compared exactly; raw IPs are not exported.'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    print(f'Report: {output}', flush=True)


if __name__ == '__main__':
    main()
