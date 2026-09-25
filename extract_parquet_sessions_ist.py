import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import pyarrow.parquet as parquet


source = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\source=stream\year=2026\month=09')
destination = Path(__file__).parent / 'stream_sessions_ist_2026-09-18_to_24.csv'
ist = timezone(timedelta(hours=5, minutes=30))
start = datetime(2026, 9, 18, tzinfo=ist).timestamp()
end = datetime(2026, 9, 25, tzinfo=ist).timestamp()
counts = Counter()

with destination.open('w', encoding='utf-8-sig', newline='') as output:
    writer = csv.writer(output)
    writer.writerow(['dateIST', 'reqTimeIST', 'cliIP', 'session_id'])

    # Include the preceding partition because early 18 September IST is still 17 September UTC.
    for day in range(17, 25):
        for path in sorted((source / f'day={day:02}').glob('*.parquet')):
            print(f'Reading {path.parent.name}/{path.name}', flush=True)
            file = parquet.ParquetFile(path)
            for batch in file.iter_batches(batch_size=65536, columns=['reqTimeSec', 'cliIP', 'queryStr']):
                times, ips, queries = (column.to_pylist() for column in batch.columns)
                for raw_time, ip, query in zip(times, ips, queries):
                    counts['input_rows'] += 1
                    if not raw_time:
                        counts['invalid_time'] += 1
                        continue
                    try:
                        epoch = float(raw_time)
                    except ValueError:
                        counts['invalid_time'] += 1
                        continue
                    if not start <= epoch < end:
                        continue
                    counts['in_ist_range'] += 1
                    sessions = parse_qs((query or '').lstrip('?'), keep_blank_values=True).get('session_id')
                    if sessions is None:
                        counts['missing_session_id'] += 1
                        continue
                    local_time = datetime.fromtimestamp(epoch, ist)
                    date_text = local_time.strftime('%d-%m-%Y')
                    time_text = local_time.strftime('%H:%M:%S')
                    for session in sessions:
                        writer.writerow([date_text, time_text, ip or '', session])
                        counts['output_rows'] += 1
                        if not session.strip():
                            counts['blank_session_id'] += 1

print(dict(counts), flush=True)
print(destination, flush=True)
