"""Validate completed dedupe, resume partitioning, and record a reusable lake receipt."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

from prepared_priority_lake import ETL, atomic_json, fingerprint, pq, sha256, verify

sys.path.insert(0, str(ETL))
from src.orchestrator.run_pipeline import PipelineRunLock, _final_clean_root


def check_final(base, day, final_clean_root=None):
    final_clean_root = final_clean_root or _final_clean_root(base)
    dedupe = json.loads((base / '.etl_02_state.json').read_text(encoding='utf-8'))
    jobs = []
    for source in ('fast', 'stream'):
        source_id = f"{source}_{day:%Y_%m_%d}"
        relative = f"source={source}/year={day:%Y}/month={day:%m}/day={day:%d}"
        final = final_clean_root / relative / f'{source_id}_final_clean.parquet'
        record = dedupe.get(source_id, {})
        rows = pq.read_metadata(final).num_rows
        if record.get('status') != 'ok' or rows <= 0 or rows != record.get('rows'):
            raise RuntimeError(f'Unverified final-clean rows for {source_id}')
        checkpoint = ETL / 'output/state/downloads' / f'{day}_{source}.json'
        download = json.loads(checkpoint.read_text(encoding='utf-8-sig'))
        if download.get('status') != 'complete' or download.get('verified') is not True:
            raise RuntimeError(f'Download is not verified for {source_id}')
        jobs.append(dict(source_id=source_id, source_key=source,
                         final_clean_file=str(final),
                         parquet_dir=str(base / 'stage/parquet' / relative)))
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--base', type=Path, default=ETL / 'data')
    parser.add_argument('--temp-dir', type=Path)
    parser.add_argument('--final-clean-root', type=Path,
                        help='Final-clean root override; otherwise use VG_ETL_FINAL_CLEAN_ROOT or local stage.')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.date >= dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date():
        raise SystemExit('Only completed past dates may be resumed.')
    jobs = check_final(args.base, args.date, args.final_clean_root)
    if args.check_only:
        print('Both final-clean files and download checkpoints are verified.', flush=True)
        return
    if not args.temp_dir:
        raise SystemExit('--temp-dir is required for partitioning.')
    lock = PipelineRunLock(ETL / 'output')
    lock.acquire()
    try:
        env = os.environ.copy()
        env.update(VG_ETL_BASE=str(args.base), VG_ETL_STAGE_JOBS=json.dumps(jobs),
                   VG_ETL_PROCESS_SOURCES=','.join(j['source_id'] for j in jobs),
                   VG_ETL_THREADS='12', VG_ETL_MEMORY='16GB', VG_ETL_COMPRESSION='ZSTD',
                   VG_ETL_DUCKDB_TEMP=str(args.temp_dir), VG_ETL_DUCKDB_MAX_TEMP='200GB')
        # Preserve successfully published files; 03.py retries only missing/failed sources.
        env.pop('VG_ETL_REPLACE_DATES', None)
        subprocess.run([sys.executable, '-u', str(ETL / 'src/pipeline/03.py')], env=env, check=True)
        receipt = dict(status='prepared', date=str(args.date), sources={})
        for job in jobs:
            source = job['source_key']
            parts = sorted((args.base / 'lake').glob(
                f"source={source}/year=*/month=*/day=*/part_{job['source_id']}_*.parquet"))
            final = Path(job['final_clean_file'])
            if not parts or pq.read_metadata(final).num_rows != sum(pq.read_metadata(p).num_rows for p in parts):
                raise RuntimeError(f'Final/lake rows do not reconcile for {source}')
            checkpoint = ETL / 'output/state/downloads' / f'{args.date}_{source}.json'
            receipt['sources'][source] = dict(final=fingerprint(final),
                lake=[fingerprint(p) for p in parts], download_checkpoint_sha256=sha256(checkpoint))
        path = ETL / 'output/state/prepared_lake' / f'{args.date}.json'
        atomic_json(path, receipt)
        verify(path, args.base)
        print(f'Prepared lake verified for {args.date}; normal recovery may reuse it.', flush=True)
    finally:
        lock.release()


if __name__ == '__main__':
    main()
