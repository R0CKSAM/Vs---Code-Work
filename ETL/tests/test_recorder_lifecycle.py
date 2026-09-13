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
