"""Retire Oct 9-11 priority staging after full lake reconciliation; keep all raw."""
import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from cleanup_daily_intermediates import (
    inspect_artifact_group, load_validation_report, parquet_rows,
    source_lake_rows, write_json_atomic,
)

ETL = Path(__file__).resolve().parents[2]
ARCHIVE = Path(r"\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE")


def checked(path, root):
    path = Path(os.path.abspath(path))
    root = root.resolve()
    if path == root or not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise RuntimeError(f"Outside cleanup root: {path}")
    for parent in [path, *path.parents]:
        if parent.is_symlink() or parent.is_junction():
            raise RuntimeError(f"Refusing link traversal: {parent}")
        if parent == root:
            break
    return path


def prepare(day):
    if day not in ('2026-10-09', '2026-10-10', '2026-10-11'):
        raise ValueError('Only the three explicitly retained priority dates are supported')
    state = json.loads((ETL / 'output/state/daily_runs' / f'{day}.json').read_text(encoding='utf-8-sig'))
    if state['status'] != 'complete':
        raise RuntimeError('Daily core run is not complete')
    load_validation_report(Path(state['validation_report']), day, ['fast', 'stream'])
    files, checks = [], []
    for source in ('fast', 'stream'):
        source_id = f"{source}_{day.replace('-', '_')}"
        partition = f'source={source}/year={day[:4]}/month={day[5:7]}/day={day[8:]}'
        final = ETL / 'data/stage/final_clean' / partition / f'{source_id}_final_clean.parquet'
        expected = parquet_rows(final)
        rows, parts = source_lake_rows([ETL / 'data/lake', ARCHIVE], source, source_id, date.fromisoformat(day))
        if expected <= 0 or expected != rows:
            raise RuntimeError(f'{source}: final/lake mismatch {expected} != {rows}')
        print(f'{day} {source}: {rows:,} rows reconciled across {len(parts)} retained lake files', flush=True)
        checks.append(dict(source=source, rows=rows, lake_files=[str(p) for p in parts]))
        stage = ETL / 'data/stage/parquet' / partition
        inspect_artifact_group(source, 'stage', stage, '.parquet', delete_root=False)
        files.extend(stage.rglob('*.parquet'))
        files.append(final)
        work = 'asrun_priority_20261012_1700' if source == 'fast' else 'stream_lake_priority_20261012_1600'
        alias = ETL / 'output/temp' / work / day / final.name
        if alias.exists():
            if not os.path.samefile(alias, final):
                raise RuntimeError(f'Priority final-clean is not the verified canonical hardlink: {alias}')
            files.append(alias)
    records = []
    for path in files:
        root = ETL / ('data/stage' if path.is_relative_to(ETL / 'data/stage') else 'output/temp')
        path = checked(path, root)
        stat = path.stat()
        records.append(dict(path=str(path), root=str(root), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns))
    return dict(date=day, status='verified', checks=checks, files=records, raw='retained', created_at=datetime.now().isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    audit = ETL / 'output/validation/stage_retirement_20261014' / f'{args.date}.json'
    if audit.exists() and json.loads(audit.read_text())['status'] == 'complete':
        print(f'{args.date}: stage retirement already complete')
        return
    plan = prepare(args.date)
    write_json_atomic(audit, plan)
    print(f"Verified {len(plan['files'])} file paths; raw/lake/DB/live outputs are not cleanup targets", flush=True)
    if not args.execute:
        return
    # The old prepared receipt requires final-clean files. Preserve it outside the
    # active receipt directory before removing the now-redundant staging links.
    receipt = ETL / 'output/state/prepared_lake' / f'{args.date}.json'
    if receipt.exists():
        retired = ETL / 'output/state/prepared_lake_retired_20261014' / receipt.name
        checked(receipt, ETL / 'output/state')
        checked(retired, ETL / 'output/state')
        retired.parent.mkdir(exist_ok=True)
        if retired.exists():
            raise RuntimeError('A retired receipt already exists; review before proceeding')
        receipt.rename(retired)
        plan['retired_receipt'] = str(retired)
    plan['status'] = 'removing_stage'
    write_json_atomic(audit, plan)
    for record in plan['files']:
        path = checked(Path(record['path']), Path(record['root']))
        stat = path.stat()
        if stat.st_size != record['bytes'] or stat.st_mtime_ns != record['mtime_ns']:
            raise RuntimeError(f'File changed since validation: {path}')
        path.unlink()
        record['removed'] = True
    plan['status'] = 'complete'
    write_json_atomic(audit, plan)
    print(f'{args.date}: verified stage removed; raw and retained lake untouched', flush=True)


if __name__ == '__main__':
    main()
