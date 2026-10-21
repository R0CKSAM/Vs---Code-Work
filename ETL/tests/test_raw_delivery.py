import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest


TOOLS = Path(__file__).resolve().parents[1] / 'src/tools'


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    import check_raw_delivery as raw
    import wait_for_complete_source as watcher
    return raw, watcher


def test_filename_and_nested_local_inventory(modules, tmp_path):
    raw, _ = modules
    nested = tmp_path / '110280'
    nested.mkdir()
    (nested / 'ak-110280-1792508322-0-ds.gz').touch()
    (nested / 'unknown.gz').touch()
    (nested / 'ignore.txt').touch()
    assert raw.filename_epoch('110280/ak-110280-1792508322-0-ds.gz') == 1792508322
    assert raw.filename_epoch('wrong-1792508322.gz') is None
    assert raw.local_inventory(tmp_path) == dict(file_count=2, timestamped_files=1, latest_epoch=1792508322)


def test_tail_threshold_missing_and_future(modules):
    raw, _ = modules
    day = date(2026, 10, 20)
    now = datetime(2026, 10, 21, 12, tzinfo=raw.IST)
    threshold = datetime(2026, 10, 20, 23, 55, tzinfo=raw.IST).timestamp()
    assert raw.assess_tail(day, threshold, now)['tail_available']
    for epoch in [None, threshold - 1, 1792508322, now.timestamp() + 301]:
        assert not raw.assess_tail(day, epoch, now)['tail_available']


def test_both_sources_required(modules):
    raw, watcher = modules
    day = datetime.now(raw.IST).date() - timedelta(days=2)
    latest = datetime.combine(day, datetime.min.time(), raw.IST).timestamp() + 86300
    complete = dict(file_count=1, latest_epoch=latest)
    incomplete = dict(file_count=1, latest_epoch=latest - 14400)
    assert watcher.ready(day, dict(fast=complete, stream=complete))
    assert not watcher.ready(day, dict(fast=complete))
    assert not watcher.ready(day, dict(fast=complete, stream=incomplete))
    assert not watcher.ready(day, dict(fast=complete, stream=dict(file_count=0, latest_epoch=latest)))


@pytest.mark.parametrize('output,code,raises', [
    ('123,110280/ak-110280-1792508322-0-ds.gz\n', 0, False),
    ('123,110280/ak-110280-1792508322-0-ds.gz\n', 1, True),
    ('bad,format,extra\n', 0, True),
    ('nonnumeric,file\n', 0, True),
])
def test_remote_inventory_fails_closed(modules, monkeypatch, tmp_path, output, code, raises):
    _, watcher = modules

    class Process:
        stdout = io.StringIO(output)
        def wait(self):
            return code
        def poll(self):
            return code

    monkeypatch.setattr(watcher.subprocess, 'Popen', lambda *args, **kwargs: Process())
    if raises:
        with pytest.raises((RuntimeError, ValueError)):
            watcher.remote_inventory('rclone', 'remote', tmp_path / 'errors.log')
    else:
        result = watcher.remote_inventory('rclone', 'remote', tmp_path / 'errors.log')
        assert result['file_count'] == 1
        assert result['bytes'] == 123
        assert result['latest_epoch'] == 1792508322


@pytest.mark.parametrize('status,validation,offset,expected', [
    ('complete', 'PASS', 1, True), ('complete', 'REVIEW', 1, True),
    ('complete', 'PASS', -1, False), ('failed', 'PASS', 1, False),
    ('complete', 'FAIL', 1, False),
])
def test_completion_must_be_fresh(modules, tmp_path, status, validation, offset, expected):
    raw, watcher = modules
    start = datetime.now(raw.IST)
    day = date(2026, 10, 20)
    path = tmp_path / 'checkpoint.json'
    path.write_text(json.dumps(dict(date=str(day), status=status, validation_status=validation,
                                   completed_at_ist=(start + timedelta(seconds=offset)).isoformat())))
    assert bool(watcher.fresh_completion(path, day, start)) is expected


def test_missing_or_invalid_checkpoint(modules, tmp_path):
    raw, watcher = modules
    path = tmp_path / 'checkpoint.json'
    assert watcher.fresh_completion(path, date.today(), datetime.now(raw.IST)) is None
    path.write_text('{')
    assert watcher.fresh_completion(path, date.today(), datetime.now(raw.IST)) is None


def test_preflight_before_conversion_and_not_microbatch():
    source = (TOOLS.parent / 'orchestrator/run_pipeline.py').read_text(encoding='utf-8')
    guard = source.index('            if not batch_id:\n                run(')
    check = source.index('check_raw_delivery.py', guard)
    loop = source.index('            for source_key, source_folder_name in daily_sources:', check)
    assert guard < check < loop
