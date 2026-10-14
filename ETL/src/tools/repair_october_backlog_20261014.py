"""Sequential, validated repairs, October 13 recovery, then dashboard refresh."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from etl_notifications import notify_failure

ETL = Path(__file__).resolve().parents[2]
WORK = ETL / 'output/temp/backlog_repair_20261014'
MART = ETL / 'output/watch_hours/concurrency'
STATE = WORK / 'state.json'
COMPLETED = []
RESUME = False
REPAIR_THREADS = 4
LOCAL_FAST_LAKE = None


def phase(name, **extra):
    payload = dict(phase=name, updated_at=datetime.now().isoformat(), completed=COMPLETED, **extra)
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temp.replace(STATE)
    print(f'{datetime.now().isoformat()} {name}', flush=True)


def run(name, args):
    phase(name)
    with (WORK / f'{name}.log').open('a', encoding='utf-8') as log:
        subprocess.run([str(a) for a in args], cwd=ETL, stdout=log, stderr=subprocess.STDOUT, check=True)


def fingerprint(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def aggregates(con, path):
    return {(source, day): (count, rows) for source, day, count, rows in con.execute(
        'SELECT source,log_date,count(*),sum(raw_ts_rows) FROM read_parquet(?) GROUP BY 1,2',
        [str(path)]).fetchall()}


def repair(day, filename, builder):
    name = f'{day}_{builder}'
    target = MART / filename
    if RESUME and any(item['date'] == day and item['step'] == builder for item in COMPLETED):
        with duckdb.connect() as con:
            con.execute('SET threads=2')
            current = aggregates(con, target).get(('fast', day))
            expected = aggregates(con, MART / 'concurrency_minute.parquet')[('fast', day)][1]
            if not current or current[1] != expected:
                raise RuntimeError(f'Previously completed repair no longer validates: {day}')
        phase('skipping_verified_repair', date=day)
        return
    stage = WORK / name
    baseline = stage / ('baseline_' + filename)
    if baseline.exists():
        if not RESUME:
            raise RuntimeError(f'Review existing repair attempt before rerunning: {stage}')
        name += '_retry_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        stage = WORK / name
        baseline = stage / ('baseline_' + filename)
    stage.mkdir(exist_ok=True)
    stamp = fingerprint(target)
    shutil.copy2(target, baseline)
    shutil.copy2(target, stage / filename)
    free = shutil.disk_usage(ETL).free
    if free < 25 * 1024**3:
        raise RuntimeError('Less than 25 GiB free; repair stopped before allocating local spill')
    lake = ETL / 'data/lake'
    archive_args = []
    if LOCAL_FAST_LAKE is not None and day == '2026-10-10':
        lake = LOCAL_FAST_LAKE
        archive_args = ['--archive-lake', lake]
    run(name, [sys.executable, ETL / f'src/tools/{builder}.py', '--lake', lake, *archive_args,
        '--out-dir', stage, '--source', 'fast', '--start', day, '--end', day,
        '--threads', str(REPAIR_THREADS), '--memory-limit', '10GB', '--temp-dir', WORK / 'scratch' / name])
    refreshed = stage / filename
    with duckdb.connect() as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='0B'")
        before, after = aggregates(con, baseline), aggregates(con, refreshed)
        key = ('fast', day)
        if {k:v for k,v in before.items() if k != key} != {k:v for k,v in after.items() if k != key}:
            raise RuntimeError('Historical totals changed outside the repaired day')
        expected = aggregates(con, MART / 'concurrency_minute.parquet')[key][1]
        if key not in after or after[key][1] != expected:
            raise RuntimeError(f'Repair does not reconcile with concurrency .ts rows: {after.get(key)} vs {expected}')
        if builder == 'build_identity_minute':
            coverage = con.execute("SELECT min(minute_ist),max(minute_ist) FROM read_parquet(?) WHERE source='fast' AND log_date=?", [str(refreshed), day]).fetchone()
            if coverage != (f'{day} 00:00:00', f'{day} 23:59:00'):
                raise RuntimeError(f'Incomplete identity coverage: {coverage}')
    if fingerprint(target) != stamp:
        raise RuntimeError('Canonical mart changed during repair; refusing overwrite')
    refreshed.replace(target)
    manifest_name = 'identity_minute_manifest.json' if builder == 'build_identity_minute' else 'fast_platform_channel_ua_device_daily_manifest.json'
    manifest = stage / manifest_name
    if manifest.exists():
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        metadata['output'] = str(target)
        manifest.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        manifest.replace(MART / manifest_name)
    COMPLETED.append(dict(date=day, step=builder, reconciled_ts_rows=expected))
    phase('repair_validated', date=day)


def dashboards():
    for name, script, args in [
        ('concurrency', 'concurrencyDashboard/generate_concurrency.py', ['--data-dir', MART, '--out', MART/'veto_concurrency.html']),
        ('audience_ops', 'audienceOpsDashboard/generate_audience_ops.py', ['--output-root', ETL/'output', '--out', ETL/'output/audience_ops/veto_audience_operations.html']),
        ('watch_hours', 'watchHoursDashboard/generate_watch_hours.py', ['--profile', ETL/'output/watch_hours/profile', '--out', ETL/'output/watch_hours/veto_watch_hours.html']),
    ]:
        run(f'refresh_{name}', [sys.executable, ETL / 'src/dashboards' / script, *args])


def main():
    global RESUME, REPAIR_THREADS, LOCAL_FAST_LAKE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--threads', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--local-fast-lake', type=Path)
    args = parser.parse_args()
    RESUME, REPAIR_THREADS, LOCAL_FAST_LAKE = args.resume, args.threads, args.local_fast_lake
    WORK.mkdir(parents=True, exist_ok=True)
    os.environ['VG_ETL_BASE'] = str(ETL)
    os.environ['PYTHONUNBUFFERED'] = '1'
    os.environ['PYTHONFAULTHANDLER'] = '1'
    process_temp = WORK / 'process_temp'
    process_temp.mkdir(exist_ok=True)
    for variable in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[variable] = str(process_temp)
    archive = Path(r'\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE')
    os.environ['VG_ASRUN_RAW_DIR'] = str(archive / 'source=AsRUN')
    for kind, folder in [('YOUTUBE', 'Youtube'), ('AMAGI', 'amagi'), ('FCT', 'FCT'), ('NCT', 'NCT')]:
        os.environ[f'VG_ASRUN_{kind}_ROOT'] = str(archive / f'source={folder}')
    import msvcrt
    lock = (WORK / 'repair.lock').open('a+b')
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    if RESUME and STATE.exists():
        previous = json.loads(STATE.read_text(encoding='utf-8'))
        COMPLETED.extend(previous.get('completed', []))
    try:
        repair('2026-10-09', 'fast_platform_channel_ua_device_daily.parquet', 'build_fast_platform_channel_ua_device')
        repair('2026-10-10', 'fast_platform_channel_ua_device_daily.parquet', 'build_fast_platform_channel_ua_device')
        repair('2026-10-12', 'identity_minute.parquet', 'build_identity_minute')
        dashboards()
        run('recovery_2026-10-13', ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            ETL/'run_recovery_pipeline.ps1', '-StartDate', '2026-10-13', '-ThroughDate', '2026-10-13'])
        daily = ETL/'output/state/daily_runs/2026-10-13.json'
        if not daily.exists() or json.loads(daily.read_text(encoding='utf-8-sig')).get('status') != 'complete':
            raise RuntimeError('October 13 core ETL did not complete; see recovery log')
        latest = json.loads((ETL/'output/state/pipeline_last_run.json').read_text(encoding='utf-8-sig'))
        if latest.get('target_date') != '2026-10-13' or latest.get('status') != 'complete':
            raise RuntimeError('October 13 downstream steps require review; refusing all-complete status')
        run('refresh_ua_preview', [sys.executable, ETL/'src/tools/generate_ua_decode_preview_dashboard.py'])
        stage = WORK/'asrun_dashboard'
        parsed = WORK/'asrun_parsed'
        shutil.copytree(ETL/'output/temp/asrun_priority_20261012_1700/parsed', parsed)
        run('refresh_asrun', [sys.executable, ETL/'asrun_demo/src/build_asrun_demo.py',
            '--channel', 'Unassigned - stakeholder mapping required', '--parsed-dir', parsed,
            '--output-dir', stage, '--identity-minute', MART/'identity_minute.parquet', '--verbose'])
        html = stage/'asrun_delivery_demo.html'
        if not html.exists() or html.stat().st_size < 1000:
            raise RuntimeError('ASRUN output missing; keeping current live output')
        live = ETL/'asrun_demo/output'
        shutil.copytree(live, WORK/'asrun_previous_dashboard')
        for path in sorted(stage.rglob('*'), key=lambda p: p.suffix == '.html'):
            if path.is_file():
                destination = live/path.relative_to(stage)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + '.publish.tmp')
                shutil.copy2(path, temporary)
                temporary.replace(destination)
        phase('complete')
    except Exception as exc:
        previous = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
        failed_step = previous.get('phase', 'repair startup')
        log_path = WORK / f'{failed_step}.log'
        phase('failed', failed_step=failed_step, log_path=str(log_path), error=str(exc))
        notify_failure(failed_step, str(exc), log_path, STATE)
        raise


if __name__ == '__main__':
    main()
