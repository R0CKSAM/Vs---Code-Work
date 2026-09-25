"""Append decoded device fields to the original first-channel report."""

import csv
import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parent
original = root / 'stream_first_watched_channel_2026-09-18_to_24.csv'
enriched = root / 'stream_first_watched_channel_with_device_2026-09-18_to_24.csv'
output = root / 'stream_first_watched_channel_device_2026-09-18_to_24.csv'
device_fields = ['device', 'device_type', 'brand', 'model', 'os', 'ua_decode_status']


def clean(value):
    value = (value or '').strip()
    if value.casefold() in {'', 'unknown', 'unknown / na', 'n/a', 'not exposed in ua'}:
        return ''
    if value.casefold().endswith('not exposed in ua'):
        return ''
    return value


with enriched.open(encoding='utf-8-sig', newline='') as stream:
    devices = {
        row['viewer_key']: {field: row[field] for field in device_fields}
        for row in csv.DictReader(stream)
    }

counts = Counter()
with original.open(encoding='utf-8-sig', newline='') as source, output.open('w', encoding='utf-8-sig', newline='') as destination:
    reader = csv.DictReader(source)
    writer = csv.DictWriter(destination, fieldnames=[*reader.fieldnames, *device_fields])
    writer.writeheader()
    for row in reader:
        decoded = devices.get(row['viewer_key'])
        if decoded is None:
            raise RuntimeError('No matching UA enrichment for viewer key')
        device_type = clean(decoded['device_type'])
        brand = clean(decoded['brand'])
        model = clean(decoded['model'])
        os = clean(decoded['os'])
        specific_model = model if model and model.casefold() != 'linux device' and not re.fullmatch(r'Android \d+(?:\.\d+)*', model, re.I) else ''
        if brand and specific_model and not specific_model.casefold().startswith(brand.casefold()):
            label = brand + ' ' + specific_model
        else:
            label = specific_model or brand or {'smart_tv': 'Smart TV', 'streaming_device': 'Streaming device'}.get(device_type, device_type.replace('_', ' ').title()) or 'Unknown'
        row.update({'device': label, 'device_type': device_type, 'brand': brand, 'model': model, 'os': os, 'ua_decode_status': decoded['ua_decode_status']})
        writer.writerow(row)
        counts['rows'] += 1
        counts['decoded_device'] += label != 'Unknown'
        counts['exact_device_id'] += row['identity_method'] == 'device_id'

if len(devices) != counts['rows']:
    raise RuntimeError('UA enrichment and original report have different viewer counts')
print(dict(counts))
print(output)
