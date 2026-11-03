"""Refresh ASRUN with completed STREAM lake dates through November 1."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import duckdb
from priority_stream_lake import ETL, atomic_json, worker_environment
from refresh_asrun_priority import publish


def main():
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    work = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\asrun_refresh') / stamp
    work.mkdir(parents=True)
    state_path = ETL / 'output/state/asrun_available_refresh.json'
    state = dict(status='starting', work=str(work), started_at=datetime.now().isoformat())
    env = worker_environment(dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1'))
    def phase(name):
        state['status'] = name
        atomic_json(state_path, state)
        print(name, flush=True)
    def run(args, name):
        logfile = work / (name + '.log')
        print(f'Log: {logfile}', flush=True)
        with logfile.open('w', encoding='utf-8') as handle:
            subprocess.run([sys.executable, '-u', *map(str, args)], cwd=ETL, env=env,
                           stdout=handle, stderr=subprocess.STDOUT, check=True)
    try:
        phase('preparing_completed_audience')
        audience = work / 'audience'
        audience.mkdir()
        baseline = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\asrun_refresh\20261102_172035\audience\identity_minute.parquet')
        shutil.copy2(baseline, audience / 'identity_minute.parquet')
        for day in ('2026-10-31', '2026-11-01'):
            phase(f'validating_stream_{day}')
            run([ETL / 'src/tools/validate_daily_delivery.py', '--lake', r'Z:\Veto Logs Backup\DO NOT DELETE',
                 '--date', day, '--sources', 'stream', '--mode', 'structural',
                 '--output-dir', work / 'validation' / day], f'validation_{day}')
            phase(f'refreshing_stream_{day}_audience')
            run([ETL / 'src/tools/build_identity_minute.py', '--lake', r'Z:\Veto Logs Backup\DO NOT DELETE',
                 '--out-dir', audience, '--source', 'stream', '--start', day, '--end', day,
                 '--threads', '8', '--memory-limit', '12GB', '--temp-dir', work / 'scratch'], f'identity_stream_{day}')
        with duckdb.connect() as con:
            con.execute('SET threads=1')
            rows = con.execute("SELECT source,log_date,count(DISTINCT minute_ist) FROM read_parquet(?) GROUP BY ALL",
                               [str(audience / 'identity_minute.parquet')]).fetchall()
        coverage = {(s, str(d)): n for s, d, n in rows}
        for day in ('2026-10-30', '2026-10-31', '2026-11-01'):
            if coverage.get(('stream', day)) != 1440:
                raise RuntimeError(f'{day} STREAM audience does not cover 1440 minutes')
        state['audience_coverage'] = {'stream_through': '2026-11-01', 'fast_through': '2026-10-29'}
        demo = ETL / 'asrun_demo'
        phase('preparing_asrun')
        parsed = work / 'parsed'
        shutil.copytree(demo / 'data/parsed', parsed)
        output = work / 'dashboard'
        inputs = sorted(Path(r'Z:\Veto Logs Backup\DO NOT DELETE\source=AsRUN').glob('ASRUN-*.txt'))
        days = sorted({datetime.strptime(p.stem[6:], '%d%m%y').date().isoformat() for p in inputs})
        unavailable = [(source, day) for day in days for source in ('fast', 'stream')
                       if coverage.get((source, day), 0) < 1440]
        state.update(asrun_through=max(days), unavailable_viewer_days=unavailable)
        args = [demo / 'src/build_asrun_demo.py', '--channel', 'Unassigned - stakeholder mapping required',
                '--identity-minute', audience / 'identity_minute.parquet', '--parsed-dir', parsed,
                '--output-dir', output, '--verbose']
        for source, day in unavailable:
            args += ['--unavailable-viewer-day', f'{source}:{day}']
        args += ['--input', *inputs]
        phase('building_asrun')
        run(args, 'asrun_build')
        html = output / 'asrun_delivery_demo.html'
        if not html.is_file() or html.stat().st_size < 1000:
            raise RuntimeError('Dashboard output missing')
        payload_path = output / 'asrun_delivery_data.js'
        payload_text = payload_path.read_text(encoding='utf-8').strip()
        payload = json.loads(payload_text.split('=', 1)[1].rstrip(';'))
        def check_references(value):
            if isinstance(value, dict):
                for item in value.values(): check_references(item)
            elif isinstance(value, list):
                for item in value: check_references(item)
            elif isinstance(value, str) and value.startswith('data/') and value.endswith('.js'):
                if not (output / value).is_file():
                    raise RuntimeError(f'Missing dashboard payload: {value}')
        check_references(payload)
        phase('publishing')
        publish(output, demo / 'output', work / 'previous_dashboard')
        state['dashboard'] = str(demo / 'output/asrun_delivery_demo.html')
        phase('complete')
    except BaseException as exc:
        state['error'] = str(exc)
        phase('failed')
        raise
    finally:
        state['finished_at'] = datetime.now().isoformat()
        atomic_json(state_path, state)


if __name__ == '__main__':
    main()
