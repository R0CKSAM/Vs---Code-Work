"""Bounded, read-only S3 polling followed by normal validated ETL recovery."""
import argparse
import csv
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time

from check_raw_delivery import IST, assess_tail, atomic_json, filename_epoch

ETL = Path(__file__).resolve().parents[2]


def remote_inventory(rclone, remote, error_path):
    count = size = matched = 0
    latest = None
    digest = hashlib.sha256()
    command = [str(rclone), 'lsf', remote, '--recursive', '--files-only', '--csv', '--format', 'sp',
               '--retries', '2', '--low-level-retries', '3', '--timeout', '2m', '--contimeout', '30s']
    with error_path.open('w', encoding='utf-8') as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding='utf-8', errors='strict')
        try:
            for row in csv.reader(process.stdout):
                if len(row) != 2:
                    raise ValueError('Unexpected remote inventory format')
                byte_count, name = int(row[0]), row[1]
                count += 1
                size += byte_count
                digest.update(json.dumps([byte_count, name], separators=(',', ':')).encode())
                epoch = filename_epoch(name)
                if epoch is not None:
                    matched += 1
                    latest = max(latest or epoch, epoch)
            code = process.wait()
            if code:
                raise RuntimeError(f'Remote listing failed ({code}); see {error_path}')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
    return dict(file_count=count, bytes=size, timestamped_files=matched,
                latest_epoch=latest, fingerprint=digest.hexdigest())


def ready(day, inventories):
    return set(inventories) == {'fast', 'stream'} and all(
        item['file_count'] > 0 and assess_tail(day, item['latest_epoch'])['tail_available']
        for item in inventories.values())


def fresh_completion(checkpoint, day, started_at):
    try:
        evidence = json.loads(checkpoint.read_text(encoding='utf-8-sig'))
        completed = datetime.fromisoformat(evidence['completed_at_ist'])
        valid = (evidence.get('status') == 'complete' and evidence.get('date') == str(day)
                 and evidence.get('validation_status') in {'PASS', 'REVIEW'}
                 and completed.tzinfo is not None and completed >= started_at)
        return evidence if valid else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--interval-seconds', type=int, default=900)
    parser.add_argument('--max-hours', type=float, default=12)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.date >= datetime.now(IST).date() or args.interval_seconds < 60 or not 0 < args.max_hours <= 24:
        parser.error('Use a past date, interval >= 60 seconds and max-hours in (0,24].')
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / 'watcher.lock').open('a+b')
    import msvcrt
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit('This source watcher is already running.')
    state = dict(date=str(args.date), started_at=datetime.now(IST).isoformat(),
                 status='checking_sources', attempts=0)
    state_path = work / 'state.json'
    deadline = time.monotonic() + args.max_hours * 3600
    while time.monotonic() < deadline:
        state.update(status='checking_sources', checked_at=datetime.now(IST).isoformat())
        atomic_json(state_path, state)
        inventories = {}
        try:
            for source, prefix in [('stream', 'veto-stream-logs'), ('fast', 'veto-fast-logs')]:
                remote = f'veto:veto-stream-logs/{prefix}/{args.date:%m/%d}'
                inventory = remote_inventory(ETL / 'tools/rclone/rclone.exe', remote, work / f'{source}_listing.err.log')
                inventory.update(assess_tail(args.date, inventory['latest_epoch']))
                inventories[source] = inventory
                state['sources'] = inventories
                atomic_json(state_path, state)
                print(f"{datetime.now(IST).isoformat()} {source}: {inventory['file_count']:,} files; "
                      f"latest={inventory['latest_file_ist']}; tail={inventory['tail_available']}", flush=True)
            state.pop('error', None)
        except Exception as exc:
            state.update(status='source_check_error', error=str(exc))
            atomic_json(state_path, state)
            print(str(exc), flush=True)
            if args.check_only:
                raise
            time.sleep(min(args.interval_seconds, max(0, deadline-time.monotonic())))
            continue
        can_run = ready(args.date, inventories)
        state['status'] = 'ready_for_recovery' if can_run else 'waiting_for_source_logs'
        atomic_json(state_path, state)
        if args.check_only:
            return
        if can_run and time.monotonic() < deadline:
            attempt_started = datetime.now(IST)
            state.update(status='recovering', attempts=state['attempts'] + 1)
            atomic_json(state_path, state)
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                       str(ETL / 'run_recovery_pipeline.ps1'), '-StartDate', str(args.date),
                       '-ThroughDate', str(args.date), '-Force']
            try:
                result = subprocess.run(command, cwd=ETL)
            except OSError as exc:
                state.update(status='recovery_failed', error=str(exc), finished_at=datetime.now(IST).isoformat())
                atomic_json(state_path, state)
                raise
            state['recovery_exit_code'] = result.returncode
            checkpoint = ETL / 'output/state/daily_runs' / f'{args.date}.json'
            evidence = fresh_completion(checkpoint, args.date, attempt_started)
            if result.returncode == 0 and evidence:
                state.update(status='recovery_finished', validation_status=evidence.get('validation_status'),
                             finished_at=datetime.now(IST).isoformat())
                atomic_json(state_path, state)
                return
            state.update(status='recovery_failed', finished_at=datetime.now(IST).isoformat())
            atomic_json(state_path, state)
            raise SystemExit('Recovery did not complete; inspect its logs. No automatic repeated heavy rerun.')
        state['next_check_seconds'] = args.interval_seconds
        atomic_json(state_path, state)
        time.sleep(min(args.interval_seconds, max(0, deadline-time.monotonic())))
    state.update(status='timed_out_waiting_for_source', finished_at=datetime.now(IST).isoformat())
    atomic_json(state_path, state)
    print('Source-wait window expired; missing data is not marked complete.', flush=True)


if __name__ == '__main__':
    main()
