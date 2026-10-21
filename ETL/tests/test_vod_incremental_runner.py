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
        return subprocess.run([
            shell, '-NoProfile', '-File', str(RUNNER), '-PlanOnly',
            '-Python', sys.executable, '-ExportsDir', str(exports),
            '-DailyStateDir', str(checkpoints), '-PipelineState', str(pipeline), *extra,
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
