"""Resume recent interrupted cleanup through the normal lake-validation guards."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo
from cleanup_daily_intermediates import load_validation_report
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrator'))
from run_pipeline import PipelineRunLock, RunRecorder


def reconcile_cleanup_run(root, audit):
    """Finish only a recorded run interrupted at its final cleanup step."""
    state_dir = root / 'output' / 'state'
    path = state_dir / 'pipeline_last_run.json'
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    steps = data.get('steps', [])
    if (data.get('status') != 'running' or not data.get('args', {}).get('cleanup_daily_intermediates')
            or not steps or steps[-1].get('step') != 'watch_hours_dashboard_html'
            or steps[-1].get('status') != 'ok'):
        return
    day = data.get('target_date', '')
    datetime.strptime(day, '%Y-%m-%d')
    datetime.strptime(data['run_id'], '%Y%m%d_%H%M%S')
    for manifest_path in sorted(audit.glob(f'cleanup_{day}_*.json'), reverse=True):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if manifest.get('mode') != 'execute':
            continue
        if manifest.get('status') != 'complete':
            return
        if manifest.get('started_at_ist', '')[:19] < steps[-1]['finished_at'][:19]:
            return
        recorder = RunRecorder.__new__(RunRecorder)
        recorder.state_dir = state_dir
        recorder.last_path = path
        recorder.run_path = state_dir / f"pipeline_run_{data['run_id']}.json"
        recorder.steps_csv = state_dir / 'pipeline_last_run_steps.csv'
        recorder.data = data
        recorder.record_step(dict(step='daily_intermediate_cleanup',status='ok',exit_code=0,
                                  allow_failure=False,started_at=manifest['started_at_ist'],
                                  finished_at=manifest['finished_at_ist'],log_path=str(manifest_path),
                                  reason='Validated cleanup resumed after interruption; original step history retained.'))
        recorder.finish('complete')
        return


def pending_manifests(audit, today):
    latest = {}
    for path in sorted(audit.glob('cleanup_*.json')):
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
        if payload.get('mode') != 'execute':
            continue
        day = datetime.strptime(payload['date'], '%Y-%m-%d').date()
        if today - timedelta(days=7) <= day < today:
            latest[day] = (path, payload)
    return [item for _, item in sorted(latest.items())
            if item[1].get('status') in {'planned', 'running', 'partial-failure'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etl-root', required=True)
    parser.add_argument('--archive-lake')
    parser.add_argument('--archive-through', help='Latest completed ETL date; keep later spillover partitions hot.')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = Path(args.etl_root).resolve(strict=True)
    base = root / 'data'
    audit = root / 'output' / 'cleanup'
    pipeline_lock = PipelineRunLock(root / 'output')
    pipeline_lock.acquire()
    today = datetime.now(ZoneInfo('Asia/Kolkata')).date()
    pending = pending_manifests(audit, today)
    print(f'Interrupted cleanup dates: {len(pending)}', flush=True)
    for manifest_path, manifest in pending:
        report = Path(manifest['validation_report']).resolve()
        if not report.is_relative_to((root / 'output' / 'validation').resolve()):
            raise RuntimeError('Cleanup validation report must be inside this ETL workspace.')
        sources = [check['source'] for check in manifest['checks']]
        candidates = [report, *sorted(report.parent.glob(f"daily_delivery_validation_{manifest['date']}_*.json"), reverse=True)]
        for candidate in candidates:
            try:
                load_validation_report(candidate, manifest['date'], sources)
                report = candidate
                break
            except (SystemExit, OSError, ValueError):
                continue
        else:
            raise RuntimeError(f"No exact passing validation report remains for {manifest['date']}.")
        command = [sys.executable, '-u', str(Path(__file__).with_name('cleanup_daily_intermediates.py')),
                   '--base', str(base), '--lake', str(base / 'lake'),
                   '--raw-root', str(base / 'raw' / 'Veto Logs Backup'),
                   '--date', manifest['date'], '--sources', ','.join(sources),
                   '--etl3-state', str(base / '.etl_03_state.json'),
                   '--validation-report', str(report), '--audit-dir', str(audit)]
        if args.archive_lake:
            command += ['--archive-lake', args.archive_lake]
        print(f"Revalidating cleanup for {manifest['date']} ({manifest_path.name})", flush=True)
        if args.execute:
            command.append('--execute')
        subprocess.run(command, check=True)
    if args.archive_through:
        through = datetime.strptime(args.archive_through, '%Y-%m-%d').date()
        if through >= today or not args.archive_lake:
            raise RuntimeError('Archive recovery requires a completed past date and an archive root.')
        archive_command = [sys.executable, '-u', str(Path(__file__).with_name('archive_lake_partitions.py')),
                           '--source-root', str(base / 'lake'), '--archive-root', args.archive_lake,
                           '--through', through.isoformat(), '--sources', 'fast,stream',
                           '--quarantine-root', str(Path(args.archive_lake) / 'delete temp' / 'lake_conflicts'),
                           '--audit-dir', str(root / 'output' / 'lake_archive')]
        # This process owns PipelineRunLock for the entire validated maintenance run.
        subprocess.run(archive_command, check=True)
        if args.execute:
            subprocess.run([*archive_command, '--execute'], check=True)
    if args.execute:
        reconcile_cleanup_run(root, audit)
    pipeline_lock.release()
    print('Cleanup recovery complete.' if args.execute else 'Cleanup recovery dry run complete.', flush=True)


if __name__ == '__main__':
    main()
