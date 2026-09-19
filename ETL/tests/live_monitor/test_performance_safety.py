import datetime as dt
import gzip
import json
import sqlite3
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ETL.src.live_monitor.config import LiveConfig
from ETL.src.live_monitor.engine import LiveEngine
from ETL.src.live_monitor.parser import FileBatch, IST, DAVIS_CUP_FEEDS, davis_cup_target
from ETL.src.live_monitor.server import SnapshotServer
from ETL.src.live_monitor.store import LiveStore


def test_all_six_assets_and_host_validation():
    for asset, prefix in DAVIS_CUP_FEEDS.items():
        now = dt.datetime.now(IST)
        assert davis_cup_target(now, 'daviscup-veto.akamaized.net:443', '/' + asset + '/segment.ts') == prefix
        assert davis_cup_target(now, 'other.example', '/' + asset + '/segment.ts') is None


def test_legacy_aliases_preserve_exact_identities_and_cutoff(tmp_path):
    store = LiveStore(tmp_path / 'db.sqlite3')
    now = dt.datetime.now(IST)
    minute = now.strftime('%Y-%m-%dT%H:%M:00%z')
    old_minute = (now-dt.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:00%z')
    for n, target in enumerate(('GRP 2/M2 | AUT vs BEL', 'GRP 7/M1 | CHL vs ESP', '3b966')):
        path = tmp_path / f'{n}.gz'
        path.write_bytes(b'test')
        store.observe_file(path, 4, path.stat().st_mtime_ns, 1)
        assert store.claim_file() == path
        batch = FileBatch(rows=1, latest_timestamp=now.timestamp())
        batch.metrics[(minute, 'host', target)] = [1, 100, 0, 0, 1] + [0]*11
        batch.minute_viewers.add((minute, 'host', target, 'shared'))
        batch.minute_devices.add((minute, 'host', target, 'device'))
        batch.minute_sessions.add((minute, 'host', target, 'session'))
        batch.minute_viewers.add((old_minute, 'host', target, 'old-only'))
        store.finish_file(path, batch)
    snapshot = store.snapshot(60)
    assert 'GRP 2/M2 | AUT vs BEL' not in snapshot['series']
    summary = snapshot['summaries']['3b966']
    assert summary['requests'] == 3
    assert summary['unique_cliips'] == 1
    assert summary['unique_device_ids'] == 1
    assert summary['unique_session_ids'] == 1
    assert snapshot['series']['3b966'][0]['active_cliips'] == 1
    selected = store.snapshot(60, ['3b966', 'GRP 2/M2 | AUT vs BEL'])
    assert selected['summaries']['__selection__'] == summary
    with store.connect() as c:
        assert c.execute('SELECT count(distinct target) FROM minute_viewers').fetchone()[0] == 3


def test_conditional_compressed_channel_snapshot(tmp_path):
    path = tmp_path / 'state.json'
    payload = {'series': {'__all__': [{'requests': 2}], 'f98c8': [{'requests': 1}]},
               'summaries': {}, 'breakdowns': {}, 'scheduled_targets': ['834dd']}
    path.write_text(json.dumps(payload), encoding='utf8')
    server = SnapshotServer('127.0.0.1', 0, path)
    server.start()
    url = f'http://127.0.0.1:{server.httpd.server_port}/api/state?channel=f98c8'
    try:
        with urlopen(Request(url, headers={'Accept-Encoding': 'gzip'})) as response:
            tag = response.headers['ETag']
            body = json.loads(gzip.decompress(response.read()))
            assert set(body['series']) == {'f98c8'}
            assert set(body['channels']) == {'__all__', 'f98c8', '834dd'}
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url, headers={'Accept-Encoding': 'gzip', 'If-None-Match': tag}))
        assert exc.value.code == 304
        assert exc.value.read() == b''
        payload['series']['f98c8'][0]['requests'] = 200
        path.write_text(json.dumps(payload), encoding='utf8')
        with urlopen(Request(url, headers={'Accept-Encoding': 'gzip', 'If-None-Match': tag})) as response:
            assert response.status == 200
            assert json.loads(gzip.decompress(response.read()))['series']['f98c8'][0]['requests'] == 200
    finally:
        server.stop()


def test_queue_lock_does_not_trigger_full_remote_redownload(tmp_path, monkeypatch):
    engine = LiveEngine(LiveConfig(state_dir=tmp_path/'state', spool_root=tmp_path/'spool'))
    monkeypatch.setattr('ETL.src.live_monitor.engine.list_recent_relative_key_sets',
                        lambda *a, **k: ([], ['existing.gz']))
    def locked(*args):
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(engine, 'observe_paths', locked)
    calls = []
    monkeypatch.setattr(engine, '_rclone', lambda *a, **k: calls.append(k))
    with pytest.raises(sqlite3.OperationalError):
        engine.sync_once()
    assert calls == []
    assert engine._runtime['last_sync_ok'] is False


def test_partial_downloads_are_queued(tmp_path, monkeypatch):
    engine = LiveEngine(LiveConfig(state_dir=tmp_path/'state', spool_root=tmp_path/'spool'))
    monkeypatch.setattr('ETL.src.live_monitor.engine.list_recent_relative_key_sets',
                        lambda *a, **k: (['new.gz'], ['new.gz']))
    monkeypatch.setattr(engine, '_rclone', lambda *a, **k: False)
    queued = []
    monkeypatch.setattr(engine, 'observe_paths', lambda paths: queued.extend(paths))
    assert engine.sync_once() is False
    assert queued and all(path.name == 'new.gz' for path in queued)


def test_health_rejects_stale_snapshot(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps({'health': {'ok': True, 'issues': []},
        'generated_at': (dt.datetime.now(IST)-dt.timedelta(minutes=20)).isoformat()}))
    server = SnapshotServer('127.0.0.1', 0, path)
    server.start()
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(f'http://127.0.0.1:{server.httpd.server_port}/healthz')
        assert error.value.code == 503
        assert 'Dashboard snapshot is stale' in json.load(error.value)['issues']
    finally:
        server.stop()


def test_early_ist_morning_reads_previous_utc_source_day(tmp_path, monkeypatch):
    engine = LiveEngine(LiveConfig(state_dir=tmp_path/'state', spool_root=tmp_path/'spool'))
    real_datetime = dt.datetime
    class Morning(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 9, 19, 4, 30, tzinfo=IST).astimezone(tz)
    monkeypatch.setattr('ETL.src.live_monitor.engine.dt.datetime', Morning)
    remotes = []
    def index(remote, *args, **kwargs):
        remotes.append(remote)
        return [], []
    monkeypatch.setattr('ETL.src.live_monitor.engine.list_recent_relative_key_sets', index)
    assert engine.sync_once()
    assert remotes and all(remote.endswith('/09/18') for remote in remotes)
