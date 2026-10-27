"""Prevent validation-only checkpoints from hiding failed reporting steps."""
import argparse
import json
from pathlib import Path


def check(root, day):
    state = root / 'output/state'
    runs = []
    for path in state.glob('pipeline_run_*.json'):
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
        if payload.get('target_date') == day and not payload.get('args', {}).get('dry_run'):
            runs.append(payload)
    if not runs:
        return  # Legacy dates still require the separate validation gate.
    run = max(runs, key=lambda item: item.get('started_at', ''))
    latest = {step['step']: step for step in run.get('steps', [])}
    failed = {name for name, step in latest.items() if step.get('status') == 'failed'}
    if run.get('status') == 'complete' and not failed:
        return
    receipt_path = state / 'reporting_repairs' / (day + '.json')
    if receipt_path.is_file() and run.get('finished_at') and failed:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
        if (receipt.get('status') == 'complete' and receipt.get('run_id') == run.get('run_id')
                and failed.issubset(set(receipt.get('repaired_steps', [])))):
            logs = receipt.get('logs', {})
            for name in failed:
                log = Path(logs.get(name, '')).resolve()
                if not log.is_relative_to((root / 'output').resolve()) or not log.is_file():
                    break
                if 'repair_exit_code=0' not in log.read_text(encoding='utf-8', errors='replace'):
                    break
            else:
                return
    raise ValueError(f'{day}: reporting not complete ({run.get("status")}); unresolved: {sorted(failed)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etl-root', type=Path, required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    try:
        check(args.etl_root.resolve(), args.date)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
