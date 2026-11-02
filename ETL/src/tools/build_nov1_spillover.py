"""Build only November 1 IST rows from verified October 31 raw inputs."""
from datetime import date, datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from priority_stream_lake import ETL, build_day, publish, atomic_json


def main():
    work = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\Temp\VetoETL\priority_nov1_spillover')
    work.mkdir(parents=True, exist_ok=True)
    state_path = ETL / 'output/state/nov1_spillover.json'
    state = dict(status='running', raw_date='2026-10-31', lake_date='2026-11-01', completed_sources=[], files=[])
    atomic_json(state_path, state)
    ist = ZoneInfo('Asia/Kolkata')
    os.environ['VG_ETL_ROW_START_EPOCH'] = str(datetime(2026, 11, 1, tzinfo=ist).timestamp())
    os.environ['VG_ETL_ROW_END_EPOCH'] = str(datetime(2026, 11, 2, tzinfo=ist).timestamp())
    try:
        for source in ('stream', 'fast'):
            source_work = work / source
            source_work.mkdir(exist_ok=True)
            lake = build_day(date(2026, 10, 31), source_work, source)
            parts = list(lake.glob('source=*/year=*/month=*/day=*/part_*.parquet'))
            expected = Path(f'source={source}/year=2026/month=11/day=01')
            if not parts or any(part.relative_to(lake).parent != expected for part in parts):
                raise RuntimeError('Spillover output contains unexpected partition dates')
            publish(lake, Path(r'Z:\Veto Logs Backup\DO NOT DELETE'), date(2026, 11, 1), state['files'], source)
            state['completed_sources'].append(source)
            atomic_json(state_path, state)
        state['status'] = 'complete'
    except BaseException as exc:
        state.update(status='failed', error=str(exc))
        raise
    finally:
        atomic_json(state_path, state)


if __name__ == '__main__':
    main()
