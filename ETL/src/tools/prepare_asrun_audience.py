"""Combine repaired ASRUN history with complete daily audience partitions."""
import argparse
import os
from pathlib import Path
import uuid

import duckdb


def prepare(baseline: Path, current: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with duckdb.connect() as con:
            con.execute('SET threads=2')
            con.execute('SET memory_limit=\'4GB\'')
            con.read_parquet(str(baseline)).create_view('baseline')
            con.read_parquet(str(current)).create_view('current_mart')
            # Replace whole source-days, never append overlapping minute counts.
            # Partial current days must not overwrite repaired full-day history.
            con.execute('''CREATE TEMP TABLE complete_days AS
                SELECT source, log_date FROM current_mart
                GROUP BY source, log_date
                HAVING count(DISTINCT minute_ist)=1440
                  AND min(substr(minute_ist,12,5))='00:00'
                  AND max(substr(minute_ist,12,5))='23:59'
            ''')
            con.execute('''COPY (
                SELECT b.* FROM baseline b
                ANTI JOIN complete_days d USING(source,log_date)
                UNION ALL BY NAME
                SELECT c.* FROM current_mart c
                JOIN complete_days d USING(source,log_date)
            ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)''', [str(temporary)])
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.baseline, args.current, args.output)
    print(f'Prepared ASRUN audience: {args.output}', flush=True)
