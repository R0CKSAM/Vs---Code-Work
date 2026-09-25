import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

source = Path(r'C:\Users\Intern\Downloads\export (7).csv')
destination = Path(__file__).parent / 'export_7_sessions_ist_with_date.csv'
ist = timezone(timedelta(hours=5, minutes=30))
epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
counts = Counter()
with source.open(encoding='utf-8-sig', newline='') as incoming, destination.open('w', encoding='utf-8-sig', newline='') as outgoing:
    writer = csv.DictWriter(outgoing, fieldnames=['session_id', 'cliIP', 'dateIST', 'reqTimeIST'])
    writer.writeheader()
    for row in csv.DictReader(incoming):
        counts['input_rows'] += 1
        params = parse_qs(row['queryStr'].lstrip('?'), keep_blank_values=True)
        sessions = params.get('session_id', [])
        if not sessions:
            counts['missing_session_id'] += 1
            continue
        if all(not value.strip() for value in sessions):
            counts['empty_session_id'] += 1
        instant = epoch + timedelta(microseconds=int(Decimal(row['reqTimeSec']) * 1000000))
        local_time = instant.astimezone(ist)
        for session in sessions:
            writer.writerow({'session_id': session, 'cliIP': row['cliIP'], 'dateIST': local_time.strftime('%d-%m-%Y'), 'reqTimeIST': local_time.strftime('%H:%M:%S')})
            counts['output_rows'] += 1
print(dict(counts))
print(destination)
