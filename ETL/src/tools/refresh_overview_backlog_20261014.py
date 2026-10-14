"""Stage and validate the Oct 9-12 Overview repair before publishing HTML."""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from repair_overview_true_source import load_lake_helpers, load_overview_module, partition_row_count

ETL = Path(__file__).resolve().parents[2]
LIVE = ETL / 'output/overview'
WORK = ETL / 'output/temp' / ('overview_repair_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
DATES = {'2026-10-09', '2026-10-10', '2026-10-11', '2026-10-12'}
SOURCES = {'fast', 'stream'}


def fingerprint(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def merge_repaired_rows(current, cached, dates, key_fields, date_field):
    """Replace only requested dates; retain later live dates verbatim."""
    selected = [row for row in cached if row[date_field] in dates]
    if {row[date_field] for row in selected} != set(dates):
        raise ValueError('Cached repair does not cover every requested date')
    result = [row for row in current if row[date_field] not in dates] + selected
    keys = [tuple(row[field] for field in key_fields) for row in result]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate keys in merged repair')
    return result


def reusable_dates(cached, dates, truth):
    counts = {(row['source'], row['date']): int(row['rows']) for row in cached}
    return [day for day in dates if all(counts.get((source, day)) == truth[(source, day)] for source in SOURCES)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-stage', type=Path, help='Reuse completed exact aggregates, checked against current lake metadata')
    args = parser.parse_args()
    WORK.mkdir(parents=True)
    stage = WORK / 'staged'
    stage.mkdir()
    env = os.environ.copy()
    env.update(VG_ETL_ARCHIVE_LAKE_ROOTS=r'\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE',
               VG_DUCKDB_THREADS='4', VG_DUCKDB_MEMORY_LIMIT='6GB',
               VG_DUCKDB_TEMP_DIR=str(WORK / 'scratch'), VG_DUCKDB_MAX_TEMP_SIZE='12GB',
               VG_OVERVIEW_IDENTITY_DEVICE_DAILY=str(ETL / 'output/identity/identity_device_daily.parquet'))
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        env[key] = str(WORK / 'process_temp')
    (WORK / 'process_temp').mkdir()
    os.environ['VG_ETL_ARCHIVE_LAKE_ROOTS'] = env['VG_ETL_ARCHIVE_LAKE_ROOTS']
    names = ['overview_source_daily.csv', 'overview_report.xlsx', 'device_daily.csv',
             'device_snapshot.csv', 'overview_dashboard.html']
    before = {name: fingerprint(LIVE / name) for name in names}
    for name in names:
        shutil.copy2(LIVE / name, stage / name)
    helpers = load_lake_helpers()
    partitions = helpers.discover_partitions(helpers.resolve_lake_roots(ETL / 'data/lake'), sources=sorted(SOURCES))
    selected = [p for p in partitions if p.date_text in DATES]
    truth = {(p.source, p.date_text): partition_row_count(p) for p in selected}
    expected = {(source, day) for source in SOURCES for day in DATES}
    if set(truth) != expected or any(rows <= 0 for rows in truth.values()):
        raise RuntimeError('Retained lake does not cover all eight required source/date pairs')
    lake_before = {path: fingerprint(path) for p in selected for path in p.files}
    current = read_rows(stage / 'overview_source_daily.csv')
    counts = {(row['source'], row['date']): int(row['rows']) for row in current}
    repair_dates = sorted({day for (source, day), rows in truth.items() if counts.get((source, day)) != rows})
    print('Repair dates: ' + ', '.join(repair_dates), flush=True)
    if repair_dates and args.reuse_stage:
        ov = load_overview_module()
        cached = read_rows(args.reuse_stage / 'overview_source_daily.csv')
        reusable = reusable_dates(cached, repair_dates, truth)
        stale = sorted(set(repair_dates) - set(reusable))
        merged = merge_repaired_rows(current, cached, reusable, ('source', 'date'), 'date')
        ov.write_source_rows_csv(stage / 'overview_source_daily.csv', sorted(merged, key=lambda r: (r['date'], r['source'])))
        ist_dates = {datetime.strptime(day, '%Y-%m-%d').strftime('%d/%m/%y') for day in reusable}
        days = merge_repaired_rows(ov.load_existing_rows(stage / 'overview_report.xlsx'),
                                   ov.load_existing_rows(args.reuse_stage / 'overview_report.xlsx'),
                                   ist_dates, ('ist_date',), 'ist_date')
        days.sort(key=lambda row: datetime.strptime(row['ist_date'], '%d/%m/%y'))
        date_range, time_range = ov.mart_date_ranges(days)
        ov.write_overview_excel(output_path=stage / 'overview_report.xlsx', data_rows=days,
                               lake_root=ETL / 'data/lake', year_filter=None, month_filter=None,
                               total_rows_pa=sum(int(r['rows']) for r in merged),
                               total_files=sum(len(p.files) for p in partitions if p.date_text <= ov.latest_completed_ist_date()),
                               date_range_ist=date_range, time_range_ist=time_range)
        print('Reused exact cached aggregates; later live dates retained.', flush=True)
        if stale:
            print('Lake changed since cached repair; rebuilding only: ' + ', '.join(stale), flush=True)
            subprocess.run([sys.executable, '-u', str(ETL / 'src/tools/repair_overview_true_source.py'),
                            '--lake-root', str(ETL / 'data/lake'), '--out-dir', str(stage),
                            '--dates', ','.join(stale)], env=env, check=True)
    elif repair_dates:
        subprocess.run([sys.executable, '-u', str(ETL / 'src/tools/repair_overview_true_source.py'),
                        '--lake-root', str(ETL / 'data/lake'), '--out-dir', str(stage),
                        '--dates', ','.join(repair_dates)], env=env, check=True)
    repaired = read_rows(stage / 'overview_source_daily.csv')
    keys = [(row['source'], row['date']) for row in repaired]
    if len(keys) != len(set(keys)):
        raise RuntimeError('Duplicate source/date summary rows')
    for key, rows in truth.items():
        actual = next((int(r['rows']) for r in repaired if (r['source'], r['date']) == key), None)
        if actual != rows:
            raise RuntimeError(f'Overview/lake mismatch: {key}: {actual} != {rows}')
    # Compare parsed values rather than CSV formatting changes from pandas.
    import pandas as pd
    old_frame = pd.read_csv(LIVE / 'overview_source_daily.csv')
    new_frame = pd.read_csv(stage / 'overview_source_daily.csv')
    old_other = old_frame[~old_frame['date'].isin(repair_dates)]
    new_other = new_frame[~new_frame['date'].isin(repair_dates)]
    pd.testing.assert_frame_equal(old_other.sort_values(['date', 'source']).reset_index(drop=True),
                                  new_other.sort_values(['date', 'source']).reset_index(drop=True), check_dtype=False)
    subprocess.run([sys.executable, '-u', str(ETL / 'src/dashboards/overViewDashboard/generate_dashboard.py'),
                    '--data-dir', str(stage)], env=env, check=True)
    html = stage / 'overview_dashboard.html'
    if html.stat().st_size < 1000:
        raise RuntimeError('Generated HTML is empty')
    # Unrelated pipeline progress is not a publication conflict. Guard the
    # actual input/output files instead, including newer dates copied above.
    if any(fingerprint(LIVE / name) != value for name, value in before.items()):
        raise RuntimeError('Live Overview changed during repair; staged files retained, publication stopped')
    if any(fingerprint(path) != value for path, value in lake_before.items()):
        raise RuntimeError('Lake changed during repair; publication stopped')
    backup = WORK / 'previous'
    backup.mkdir()
    for name in ('overview_source_daily.csv', 'overview_report.xlsx', 'overview_dashboard.html'):
        shutil.copy2(LIVE / name, backup / name)
        os.replace(stage / name, LIVE / name)
    (WORK / 'complete.json').write_text(json.dumps({'status': 'complete', 'dates': sorted(DATES),
        'validated_source_dates': len(truth), 'published_at': datetime.now().isoformat()}, indent=2))
    print('COMPLETE: Overview summary and HTML published; all 8 source/date counts match retained lake.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        sys.path.insert(0, str(ETL / 'src/runtime'))
        from etl_notifications import notify_failure
        notify_failure('Overview Oct 9-12 refresh', str(exc), log_path=ETL / 'output/temp/overview_repair_20261014.out.log')
        raise
