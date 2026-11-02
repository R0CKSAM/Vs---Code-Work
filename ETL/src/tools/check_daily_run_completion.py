"""Prevent validation-only checkpoints from hiding failed reporting steps."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrator'))
from run_pipeline import _cleanup_has_review_only


def review_only_cleanup(root, run, latest, day):
    """Recognize intentional retention, never an arbitrary cleanup failure."""
    step = latest.get('daily_intermediate_cleanup', {})
    if not step.get('allow_failure') or not run.get('finished_at'):
        return False
    log = Path(step.get('log_path', '')).resolve()
    if not log.is_relative_to((root / 'output').resolve()) or not log.is_file():
        return False
    if 'Cleanup refused: a full PASS validation report is required.' not in log.read_text(encoding='utf-8', errors='replace'):
        return False
    reports = root / 'output/validation/daily_delivery'
    for report in reports.glob(f'daily_delivery_validation_{day}_*.json'):
        payload = json.loads(report.read_text(encoding='utf-8-sig'))
        generated = payload.get('generated_at_ist', '')[:19]
        if (run.get('started_at', '')[:19] <= generated <= run['finished_at'][:19]
                and _cleanup_has_review_only(report, day, ['fast', 'stream'])):
            return True
    return False


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
    if (run.get('status') == 'complete_with_warnings'
            and failed == {'daily_intermediate_cleanup'}
            and all(step.get('status') in {'ok', 'skipped', 'failed'} for step in latest.values())
            and review_only_cleanup(root, run, latest, day)):
        print(f'{day}: reporting complete; channel REVIEW remains open, raw/stage inputs retained.')
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
