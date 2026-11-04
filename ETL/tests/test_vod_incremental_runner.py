import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'ETL/run_vod_query_dashboard_incremental.ps1'


@pytest.fixture
def plan(tmp_path):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    exports = tmp_path / 'exports'
    data = exports / 'vod_stream_query_analysis_dashboard_data'
    data.mkdir(parents=True)
    (data / '2026-10-17.js').touch()
    (exports / 'vod_stream_query_analysis_dashboard.html').write_text(
        'const dashboardIndex={"dates":["2026-10-17"]};\n')
    checkpoints = tmp_path / 'daily_runs'
    checkpoints.mkdir()
    for day, validation in [('18', 'PASS'), ('19', 'REVIEW')]:
        (checkpoints / f'2026-10-{day}.json').write_text(json.dumps(dict(
            date=f'2026-10-{day}', status='complete', validation_status=validation)))
    pipeline = tmp_path / 'pipeline.json'
    pipeline.write_text(json.dumps(dict(status='failed', target_date='2026-10-20')))

    def run(*extra):
        validation_args = [] if '-ValidationRoot' in extra else ['-ValidationRoot', str(tmp_path / 'no_validation')]
        return subprocess.run([
            shell, '-NoProfile', '-File', str(RUNNER), '-PlanOnly',
            '-Python', sys.executable, '-ExportsDir', str(exports),
            '-DailyStateDir', str(checkpoints), '-PipelineState', str(pipeline), *validation_args, *extra,
        ], text=True, capture_output=True)

    return run, checkpoints, pipeline


def test_failed_latest_run_uses_completed_days(plan):
    run, _, _ = plan
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18, 2026-10-19' in result.stdout
    assert '2026-10-20' not in result.stdout


def test_explicit_date_cannot_bypass_completion(plan):
    run, _, _ = plan
    result = run('-Date', '2026-10-20')
    assert result.returncode != 0
    assert 'exceeds completed ETL date' in result.stderr


def test_missing_intermediate_checkpoint_blocks_refresh(plan):
    run, checkpoints, _ = plan
    (checkpoints / '2026-10-18.json').unlink()
    result = run()
    assert result.returncode != 0
    assert 'No completed ETL evidence for 2026-10-18' in result.stderr


def test_failed_daily_checkpoint_cannot_be_used(plan):
    run, checkpoints, _ = plan
    (checkpoints / '2026-10-19.json').write_text(json.dumps(dict(
        date='2026-10-19', status='failed', validation_status='FAIL')))
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18' in result.stdout
    assert '2026-10-19' not in result.stdout


def test_pipeline_completion_is_accepted_for_its_exact_day(plan):
    run, checkpoints, pipeline = plan
    (checkpoints / '2026-10-19.json').unlink()
    pipeline.write_text(json.dumps(dict(status='complete_with_warnings', target_date='2026-10-19')))
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18, 2026-10-19' in result.stdout


def test_orphan_payload_does_not_count_as_published(plan):
    run, checkpoints, _ = plan
    data = checkpoints.parent / 'exports/vod_stream_query_analysis_dashboard_data'
    (data / '2026-10-19.js').touch()
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18, 2026-10-19' in result.stdout


def test_approved_gap_is_included_without_blocking_later_day(plan):
    run, checkpoints, _ = plan
    (checkpoints / '2026-10-18.json').unlink()
    incidents = checkpoints.parent / 'incidents'
    incidents.mkdir()
    approval = checkpoints.parent / 'approval.json'
    approval.write_text(json.dumps(dict(kind='operator_confirmed_cdn_loss', dates=['2026-10-18'],
        sources=['stream', 'fast'], dashboard_policy='exclude_partial_days', reason='Confirmed outage',
        confirmed_at='2026-10-20')))
    receipt = dict(date='2026-10-18', status='processed_with_confirmed_source_gap',
                   full_day_complete=False, dashboard_eligible=False, approval=str(approval))
    path = incidents / '2026-10-18.json'
    path.write_text(json.dumps(receipt))
    result = run('-IncidentStateDir', str(incidents))
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18, 2026-10-19' in result.stdout
    assert 'missing hours are not zero traffic' in result.stdout
    exports = checkpoints.parent / 'exports'
    (exports / 'vod_stream_query_analysis_dashboard_data/2026-10-19.js').touch()
    (exports / 'vod_stream_query_analysis_dashboard.html').write_text(
        'const dashboardIndex={"dates":["2026-10-17","2026-10-19"]};\n')
    result = run('-IncidentStateDir', str(incidents))
    assert result.returncode == 0, result.stderr
    assert 'Dates to append: 2026-10-18' in result.stdout
    receipt['dashboard_eligible'] = True
    path.write_text(json.dumps(receipt))
    result = run('-IncidentStateDir', str(incidents))
    assert result.returncode != 0
    assert 'Invalid source-gap receipt' in result.stderr


@pytest.mark.parametrize('condition', ['valid', 'partial', 'wrong_source', 'changed_file', 'extra_file'])
def test_imported_stream_validation_matches_current_partition(plan, condition):
    from datetime import datetime, timezone, timedelta
    run, checkpoints, _ = plan
    (checkpoints / '2026-10-18.json').unlink()
    root = checkpoints.parent
    lake = root / 'stream'
    partition = lake / 'year=2026/month=10/day=18'
    partition.mkdir(parents=True)
    part = partition / 'part_stream_2026_10_18_0.parquet'
    part.write_bytes(b'test fixture: metadata is trusted from validator')
    validation = root / 'validation'
    validation.mkdir()
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    if condition == 'changed_file':
        now -= timedelta(days=1)
    report = dict(date='2026-10-18', overall_status='PASS', generated_at_ist=now.isoformat(),
                  source_results=[dict(source='fast' if condition == 'wrong_source' else 'stream',
                     status='PASS', hard_failure=False,
                     selected=dict(date='2026-10-18', full_day=condition != 'partial', files=[dict(path=str(part))]))])
    (validation / 'daily_delivery_validation_2026-10-18_test.json').write_text(json.dumps(report))
    if condition == 'extra_file':
        (partition / 'part_stream_extra.parquet').touch()
    result = run('-ValidationRoot', str(validation), '-LakeRoot', str(lake), '-FallbackLakeRoot', str(root / 'absent'))
    if condition == 'valid':
        assert result.returncode == 0, result.stderr
        assert 'Validated STREAM lake accepted for 2026-10-18' in result.stdout
    else:
        assert result.returncode != 0
        assert 'No completed ETL evidence for 2026-10-18' in result.stderr
