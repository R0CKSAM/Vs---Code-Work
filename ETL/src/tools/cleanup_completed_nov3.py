"""Audited cleanup of completed Oct 31 STREAM and abandoned scratch only."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import psutil
import pyarrow.parquet as pq

ETL = Path(__file__).resolve().parents[2]
ARCHIVE = Path(r'Z:\Veto Logs Backup\DO NOT DELETE').resolve()
TEMP = ARCHIVE / 'Temp/VetoETL'
WORK = TEMP / 'ITVINTERN03/stream_20261031'


def validate():
    run = json.loads((ETL / 'output/state/oct31_stream_only_last_run.json').read_text())
    report = json.loads((ETL / 'output/validation/oct31_stream_only/daily_delivery_validation_latest.json').read_text())
    assert run['status'] == 'complete' and run['target_date'] == '2026-10-31'
    assert report['overall_status'] == 'PASS' and report['date'] == '2026-10-31'
    state = json.loads((WORK / '.etl_03_state.json').read_text())
    record = state['stream_2026_10_31_final_clean.parquet']
    assert record['status'] == 'ok'
    files = []
    for day in ('month=10/day=31', 'month=11/day=01'):
        files.extend((ARCHIVE / 'source=stream/year=2026' / day).glob('part_stream_2026_10_31_*.parquet'))
    rows = sum(pq.read_metadata(p).num_rows for p in files)
    assert rows == record['rows'] and rows > 0, 'Lake/state rows differ'
    final = WORK / 'final_clean/source=stream/year=2026/month=10/day=31/stream_2026_10_31_final_clean.parquet'
    if final.exists():
        assert pq.read_metadata(final).num_rows == rows, 'Final/lake rows differ'
    return dict(rows=rows, lake_files=[str(p) for p in files])


def targets():
    return [
        ETL / 'data/stage/parquet/source=stream/year=2026/month=10/day=31',
        WORK / 'stage', WORK / 'duckdb', WORK / 'final_clean',
        TEMP / 'priority_nov1_spillover',
        TEMP / 'asrun_refresh/20261103_102423/scratch',
        TEMP / 'asrun_refresh/20261102_172035/scratch',
        ETL / 'data/raw/Veto Logs Backup/Veto Stream Backup/10/31',
    ]


def check_path(path):
    resolved = path.resolve()
    assert resolved != TEMP and resolved != ETL
    assert resolved.is_relative_to(ETL / 'data') or resolved.is_relative_to(TEMP)
    assert not path.is_symlink() and not path.is_junction(), f'Refusing link: {path}'
    for process in psutil.process_iter(['pid', 'cmdline']):
        if process.pid == os.getpid(): continue
        command = ' '.join(process.info['cmdline'] or []).casefold()
        assert str(path).casefold() not in command and str(resolved).casefold() not in command, f'Active process uses {path}'
    return resolved


def inventory(path):
    count = size = 0
    for folder, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            child = Path(folder) / name
            assert not child.is_symlink() and not child.is_junction(), f'Nested link: {child}'
        for name in files:
            size += (Path(folder) / name).stat().st_size
            count += 1
    return count, size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    audit = ETL / 'output/cleanup' / ('nov3_space_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
    state = dict(mode='execute' if args.execute else 'plan', status='running', evidence=validate(), groups=[])
    def save():
        audit.write_text(json.dumps(state, indent=2))
    save()
    try:
        for path in targets():
            if not path.exists(): continue
            resolved = check_path(path)
            print(f'Inspecting {resolved}', flush=True)
            count, size = inventory(resolved)
            item = dict(path=str(resolved), files=count, bytes=size, status='planned')
            state['groups'].append(item)
            save()
            print(f'{count:,} files; {size / 1024**3:.2f} GiB', flush=True)
            if args.execute:
                check_path(resolved)
                shutil.rmtree(resolved)
                item['status']='removed'
                save()
                print('Removed', flush=True)
        state['status']='complete'
    except BaseException as exc:
        state.update(status='failed', error=str(exc))
        raise
    finally:
        save()
        print(f'Audit: {audit}', flush=True)


if __name__ == '__main__': main()
