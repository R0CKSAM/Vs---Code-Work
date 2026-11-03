"""Validate every referenced published data file and its date partition."""
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

ETL = Path(__file__).resolve().parents[2]
ROOT = ETL / 'asrun_demo/output'

def decode(path):
    text = path.read_text(encoding='utf-8').strip()
    body = text.split(']=', 1)[1] if ']=' in text[:200] else text.split('=', 1)[1]
    value, end = json.JSONDecoder().raw_decode(body)
    tail = body[end:].strip().lstrip(';').strip()
    if tail:
        # NCT partitions intentionally contain a second audience assignment.
        if not tail.startswith('window.__NCT_AUDIENCE_PARTITIONS__='):
            raise ValueError('Unexpected trailing JavaScript')
        audience = json.loads(tail.split(']=', 1)[1].rstrip(';'))
        return {'segments': value, 'audience': audience}
    return value

def main():
    core = decode(ROOT / 'asrun_delivery_data.js')
    files = {}
    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and urlsplit(item).path.endswith('.js'):
                    files[urlsplit(item).path] = key if len(key) == 10 and key[:4].isdigit() else None
                else:
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    references(core)
    pending = list(files)
    checked = set()
    errors = []
    row_count = 0
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        checked.add(name)
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            errors.append(f'Outside output: {name}')
            continue
        try:
            data = decode(path)
            before = set(files)
            references(data)
            pending.extend(set(files) - before)
            arrays = [data] if isinstance(data, list) else [v for v in data.values() if isinstance(v, list)]
            for rows in arrays:
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    row_count += 1
                    day = files[name]
                    actual = row.get('log_date')
                    if day and actual and str(actual)[:10] != day:
                        errors.append(f'Wrong partition {name}: {actual}')
                    for key in ('concurrent_viewers', 'avg_concurrent_viewers', 'peak_concurrent_viewers'):
                        number = row.get(key)
                        if number is not None and (not math.isfinite(float(number)) or float(number) < 0):
                            errors.append(f'Invalid {key} in {name}')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    result = dict(files_checked=len(checked), rows_checked=row_count, errors=errors,
                  passed=not errors, unavailable_viewer_days=core['unavailable_viewer_days'])
    destination = ETL / 'output/validation/asrun_payload_audit.json'
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'unavailable_viewer_days'}))
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
