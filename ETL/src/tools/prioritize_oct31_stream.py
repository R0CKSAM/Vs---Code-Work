"""Process October 31 STREAM before resuming the serial lake queue."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'output/state/priority_oct31_stream.json'


def main():
    if STATE.exists():
        raise RuntimeError('Priority request already exists; inspect it before restarting.')
    parent = psutil.Process(8568)
    if not any('run_lake_priority.ps1' in part for part in parent.cmdline()):
        raise RuntimeError('Lake coordinator PID changed.')
    if (ROOT / 'output/state/pipeline.lock').exists():
        raise RuntimeError('A lake writer is active; priority must wait for a safe boundary.')
    state = dict(status='waiting_for_download', source='stream', date='2026-10-31',
                 held_pid=parent.pid, held_created=parent.create_time(),
                 full_day_validated=False, reporting_deferred=True)

    def save():
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(STATE)

    parent.suspend()  # Download workers remain active; only the serial coordinator waits.
    try:
        if (ROOT / 'output/state/pipeline.lock').exists():
            raise RuntimeError('Writer started during the priority handoff.')
        save()
        receipt = ROOT / 'output/state/downloads/2026-10-31_stream.json'
        deadline = time.monotonic() + 24 * 3600
        while True:
            if receipt.exists():
                data = json.loads(receipt.read_text(encoding='utf-8-sig'))
                if data.get('status') == 'failed':
                    raise RuntimeError('Priority STREAM download failed; inspect download log.')
                if (data.get('verified') is True and data.get('status') == 'complete'
                        and data.get('date') == '2026-10-31' and data.get('source') == 'stream'
                        and data.get('local_count', 0) > 0
                        and data['local_count'] == data['remote_count']
                        and data['local_bytes'] == data['remote_bytes']):
                    break
            if time.monotonic() >= deadline:
                raise RuntimeError('Priority download did not verify within 24 hours.')
            time.sleep(15)
        state['status'] = 'processing'
        save()
        env = dict(os.environ)
        env['VG_ETL_FINAL_CLEAN_ROOT'] = r'Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\final_clean'
        command = [sys.executable, '-u', str(ROOT / 'src/orchestrator/run_pipeline.py'),
                   '--base', str(ROOT / 'data'), '--etl1-daily-date', '2026-10-31',
                   '--etl1-sources', 'stream', '--etl1-daily-raw-root', str(ROOT / 'data/raw/Veto Logs Backup'),
                   '--state-name', 'priority_oct31_stream', '--etl1-workers', '12',
                   '--etl1-compression', 'snappy', '--stage-threads', '12', '--stage-memory', '24GB',
                   '--stage-max-temp-size', '200GB', '--stage-compression', 'snappy',
                   '--deep-profile-temp-dir', r'Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\duckdb\deep_profile',
                   '--lake-repair-lookback-days', '0']
        # This out-of-order source load still performs raw preflight and exact
        # final-clean/lake row reconciliation. Full-day coverage needs Oct 30
        # spillover and is checked by the normal serial queue afterwards.
        command += ['--skip-' + name for name in (
            'watch', 'overview', 'deep-profile', 'device-snapshot', 'device-decode-profile',
            'concurrency', 'latency', 'identity-mart', 'content-mart', 'audience', 'master', 'data-validation')]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        state['status'] = 'source_lake_complete'
    except BaseException as exc:
        state.update(status='failed', error=str(exc))
        raise
    finally:
        try:
            if parent.is_running() and parent.create_time() == state['held_created']:
                parent.resume()
                state['normal_queue_resumed'] = True
        finally:
            save()


if __name__ == '__main__':
    main()
