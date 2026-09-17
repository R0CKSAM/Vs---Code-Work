import datetime as dt

from ETL.src.live_monitor.parser import IST, FileBatch, davis_cup_target
from ETL.src.live_monitor.store import LiveStore


def test_shared_asset_switches_only_at_scheduled_start():
    host = 'daviscup-veto.akamaized.net'
    path = '/3b9668eaa10546528bc10dc0fbaf23bd/playlist.m3u8'
    assert davis_cup_target(dt.datetime(2026, 9, 19, 14, 29, tzinfo=IST), host, path) is None
    assert davis_cup_target(dt.datetime(2026, 9, 19, 14, 30, tzinfo=IST), host, path) == 'GRP 2/M2 | AUT vs BEL'
    assert davis_cup_target(dt.datetime(2026, 9, 19, 21, 29, tzinfo=IST), host, path) == 'GRP 2/M2 | AUT vs BEL'
    assert davis_cup_target(dt.datetime(2026, 9, 19, 21, 30, tzinfo=IST), host, path) == 'GRP 7/M1 | CHL vs ESP'
    assert davis_cup_target(dt.datetime(2026, 9, 17, 21, 30, tzinfo=IST), host, path) is None
    assert davis_cup_target(dt.datetime(2026, 9, 19, 21, 30, tzinfo=IST), 'different-host', path) is None


def test_selection_deduplicates_people_and_weights_timing(tmp_path):
    store = LiveStore(tmp_path / 'state.sqlite3')
    minute = dt.datetime.now(IST).replace(second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:00%z')
    for channel, viewers, samples, total in [('A', ['shared', 'a'], 1, 100), ('B', ['shared', 'b'], 3, 900)]:
        path = tmp_path / (channel + '.gz')
        path.write_bytes(b'test')
        store.observe_file(path, 4, path.stat().st_mtime_ns, 1)
        store.claim_file()
        batch = FileBatch(rows=samples, latest_timestamp=dt.datetime.now().timestamp())
        batch.metrics[(minute, 'host', channel)] = [samples, 100, 0, 0, 1, samples, total, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for viewer in viewers:
            batch.minute_viewers.add((minute, 'host', channel, viewer))
        store.finish_file(path, batch)
    before = store.snapshot(360)
    result = store.snapshot(360, ['A', 'B', 'A'])
    combined = result['summaries']['__selection__']
    assert combined['unique_cliips'] == 3
    assert combined['requests'] == 4
    assert combined['ttfb_avg_ms'] == 250
    assert result['series']['__selection__'][0]['active_cliips'] == 3
    assert store.snapshot(360)['summaries'] == before['summaries']
