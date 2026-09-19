import importlib.util
import io
from pathlib import Path
from unittest.mock import Mock


def test_shutdown_closes_ffmpeg_and_rejects_new_recordings(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'recorder/recorder_server.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('recorder_lifecycle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    channels = tmp_path / 'channels.json'
    channels.write_text('[]')
    manager = module.RecorderManager(channels, tmp_path / 'recordings', tmp_path / 'state.sqlite')
    assert manager.system_status()['stopping'] is False
    process = Mock()
    process.stdin = io.StringIO()
    manager.processes['test-recording'] = process
    manager.store = Mock()
    manager.shutdown()
    assert manager.stopping is True
    assert process.stdin.getvalue() == 'q\n'
    process.wait.assert_called_once_with(timeout=12)
    process.terminate.assert_not_called()
    assert not manager.processes
    manager.ffmpeg = 'fake-ffmpeg'
    manager.channels = {'one': {'id': 'one', 'name': 'One', 'enabled': True}}
    manager._start_one = Mock()
    # Disk usage does not affect the shutdown gate under test.
    monkeypatch.setattr(module.shutil, 'disk_usage', Mock(return_value=Mock(free=10 * 1024**3)))
    result = manager.start(['one'])
    assert result['errors'][0]['reason'] == 'Recorder is shutting down'
    manager._start_one.assert_not_called()


def load_recorder(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'recorder/recorder_server.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('recorder_safety', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stale_or_empty_target_does_not_stop_other_recordings(tmp_path, monkeypatch):
    module = load_recorder(monkeypatch)
    channels = tmp_path / 'channels.json'
    channels.write_text('[]')
    manager = module.RecorderManager(channels, tmp_path / 'recordings', tmp_path / 'state.sqlite')
    process = Mock()
    manager.processes['active'] = process
    manager.channel_jobs['other-channel'] = 'active'
    assert manager.stop(channel_ids=['already-stopped']) == {'stopped': []}
    assert manager.stop(channel_ids=[]) == {'stopped': []}
    assert manager.stop(recording_ids=[]) == {'stopped': []}
    assert manager.stop(recording_ids=['old-id']) == {'stopped': []}
    process.wait.assert_not_called()
    assert manager.processes == {'active': process}


def test_active_list_and_restart_marks_interrupted(tmp_path, monkeypatch):
    module = load_recorder(monkeypatch)
    channels = tmp_path / 'channels.json'
    channels.write_text('[]')
    db_path = tmp_path / 'state.sqlite'
    manager = module.RecorderManager(channels, tmp_path / 'recordings', db_path)
    row = dict(id='active', channel_id='one', channel_name='One', status='recording',
               started_at=module.now_text(), output_pattern='test_%03d.mkv', pid=123, error='')
    manager.store.insert(row)
    manager.processes['active'] = Mock(poll=Mock(return_value=None))
    assert manager.active_recordings()[0]['id'] == 'active'
    manager.processes['active'].poll.return_value = 1
    assert manager.active_recordings() == []
    reopened = module.RecorderStore(db_path)
    assert reopened.recent()[0]['status'] == 'interrupted'
