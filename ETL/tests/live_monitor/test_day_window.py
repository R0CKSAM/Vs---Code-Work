import concurrent.futures
import datetime as dt
import gzip
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ETL.src.live_monitor.config import LiveConfig
from ETL.src.live_monitor.parser import FileBatch, IST
from ETL.src.live_monitor.server import SnapshotServer
from ETL.src.live_monitor.store import LiveStore


def test_default_is_today_and_rolling_override_is_available(monkeypatch):
    monkeypatch.delenv('VETO_LIVE_DASHBOARD_MINUTES', raising=False)
    assert LiveConfig().dashboard_minutes == 0
    monkeypatch.setenv('VETO_LIVE_DASHBOARD_MINUTES', '360')
    assert LiveConfig().dashboard_minutes == 360


def test_today_starts_at_ist_midnight_and_rolls_over_without_restart(tmp_path):
    store = LiveStore(tmp_path / 'day.sqlite3')
    now = dt.datetime(2026, 9, 19, 23, 59, tzinfo=IST)
    for n, minute in enumerate(('2026-09-18T23:59:00+0530', '2026-09-19T00:00:00+0530',
                                '2026-09-19T18:00:00+0530', '2026-09-19T23:59:00+0530',
                                '2026-09-20T00:00:00+0530')):
        path = tmp_path / f'{n}.gz'
        path.write_bytes(b'test')
        store.observe_file(path, 4, path.stat().st_mtime_ns, 1)
        assert store.claim_file() == path.resolve()
        batch = FileBatch(rows=1, latest_timestamp=now.timestamp())
        for target in ('__all__', 'A'):
            batch.metrics[(minute, 'host', target)] = [1, 100, 0, 0, 1] + [0] * 11
            batch.minute_viewers.add((minute, 'host', target, 'returning-viewer'))
        store.finish_file(path, batch)
    snapshot = store.snapshot(0, now=now)
    assert snapshot['window_start_ist'] == '2026-09-19T00:00:00+0530'
    assert snapshot['window_minutes'] == 1440
    assert snapshot['summaries']['A']['requests'] == 3
    assert snapshot['summaries']['A']['unique_cliips'] == 1
    assert snapshot['summaries']['A']['returning_cliips'] == 1
    assert store.snapshot(0, ['A'], now=now)['summaries']['__selection__'] == snapshot['summaries']['A']
    tomorrow = store.snapshot(0, now=now + dt.timedelta(minutes=1))
    assert tomorrow['window_start_ist'] == '2026-09-20T00:00:00+0530'
    assert tomorrow['window_minutes'] == 1
    assert tomorrow['summaries']['A']['requests'] == 1
    assert store.snapshot(360, now=now)['summaries']['A']['requests'] == 2


def test_selection_skips_global_file_ledger(tmp_path, monkeypatch):
    store = LiveStore(tmp_path / 'db.sqlite3')
    queries = []
    original = store.connect
    import contextlib

    @contextlib.contextmanager
    def traced(write=True):
        with original(write=write) as connection:
            connection.set_trace_callback(queries.append)
            yield connection

    monkeypatch.setattr(store, 'connect', traced)
    store.snapshot(0, ['A', 'B'])
    assert not any('FROM files' in query for query in queries)


def test_channel_payload_keeps_shared_timeline(tmp_path):
    path = tmp_path / 'state.json'
    row = {'minute_ist': '2026-09-19T23:58:00+0530', 'requests': 123, 'active_cliips': 8}
    path.write_text(json.dumps({'series': {'__all__': [row], 'A': []}, 'summaries': {},
                               'window_start_ist': '2026-09-19T00:00:00+0530'}), encoding='utf8')
    server = SnapshotServer('127.0.0.1', 0, path)
    server.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.httpd.server_port}/api/state?channel=A') as response:
            result = json.load(response)
        assert set(result['series']) == {'A'}
        assert result['timeline'] == [{'minute_ist': row['minute_ist'], 'requests': 123}]
        assert result['window_start_ist'].endswith('T00:00:00+0530')
    finally:
        server.stop()


def test_multichannel_cache_coalesces_lan_users_and_invalidates_on_new_snapshot(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text('{}', encoding='utf8')
    calls = []
    entered, release = threading.Event(), threading.Event()

    def calculate(targets):
        calls.append(targets)
        entered.set()
        assert release.wait(5)
        return {'series': {'__selection__': []}, 'summaries': {}, 'breakdowns': {}}

    server = SnapshotServer('127.0.0.1', 0, path, calculate)
    server.start()
    url = f'http://127.0.0.1:{server.httpd.server_port}/api/selection?channel=B&channel=A&channel=A'

    def fetch():
        with urlopen(Request(url, headers={'Accept-Encoding': 'gzip'}), timeout=10) as response:
            return response.headers['ETag'], json.loads(gzip.decompress(response.read()))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as clients:
            first = clients.submit(fetch)
            assert entered.wait(5)
            second = clients.submit(fetch)
            time.sleep(.05)
            release.set()
            tag, result = first.result(timeout=10)
            assert second.result(timeout=10) == (tag, result)
        assert calls == [['A', 'B']]
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url, headers={'Accept-Encoding': 'gzip', 'If-None-Match': tag}))
        assert exc.value.code == 304
        path.write_text('{"revision":2}', encoding='utf8')
        fetch()
        assert calls == [['A', 'B'], ['A', 'B']]
    finally:
        release.set()
        server.stop()
