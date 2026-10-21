"""Fail early when Akamai raw filenames cannot cover the target IST day's tail.

This is a necessary-input check, not a replacement for lake coverage validation.
"""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NAME = re.compile(r"^ak-\d+-(\d{10})-\d+-ds\.gz$")


def filename_epoch(name):
    match = NAME.fullmatch(Path(name).name)
    return int(match[1]) if match else None


def assess_tail(day, latest, now=None):
    now = now or datetime.now(timezone.utc)
    required = datetime.combine(day + timedelta(days=1), time(), IST) - timedelta(minutes=5)
    valid = latest is not None and required.timestamp() <= latest <= now.timestamp() + 300
    return dict(tail_available=valid, required_tail_ist=required.isoformat(),
                latest_file_ist=datetime.fromtimestamp(latest, IST).isoformat() if latest else None)


def local_inventory(root):
    count = matched = 0
    latest = None
    for directory, _, names in os.walk(root):
        for name in names:
            if not name.endswith('.gz'):
                continue
            count += 1
            epoch = filename_epoch(name)
            if epoch is not None:
                matched += 1
                latest = max(latest or epoch, epoch)
    return dict(file_count=count, timestamped_files=matched, latest_epoch=latest)


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--raw-root', required=True, type=Path)
    parser.add_argument('--sources', default='fast,stream')
    parser.add_argument('--fast-name', default='Veto fast Backup')
    parser.add_argument('--stream-name', default='Veto Stream Backup')
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    sources = args.sources.split(',')
    if args.date >= datetime.now(IST).date() or not sources or set(sources) - {'fast', 'stream'}:
        parser.error('Use a completed past date and fast/stream sources.')
    results = []
    for source in sources:
        folder = args.fast_name if source == 'fast' else args.stream_name
        path = args.raw_root / folder / f'{args.date:%m/%d}'
        inventory = local_inventory(path)
        result = dict(source=source, path=str(path), **inventory,
                      **assess_tail(args.date, inventory['latest_epoch']))
        results.append(result)
        print(f"{source}: latest raw file={result['latest_file_ist']}; "
              f"required >= {result['required_tail_ist']}; tail_available={result['tail_available']}", flush=True)
    passed = all(result['tail_available'] for result in results)
    atomic_json(args.report, dict(date=str(args.date), checked_at=datetime.now(IST).isoformat(),
                                 status='candidate_tail_available' if passed else 'incomplete_raw_delivery',
                                 sources=results))
    if not passed:
        raise SystemExit('Raw delivery is incomplete. Retaining all inputs; restore the missing source logs before retrying ETL.')


if __name__ == '__main__':
    main()
