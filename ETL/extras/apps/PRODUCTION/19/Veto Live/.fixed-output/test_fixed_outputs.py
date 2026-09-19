import ast
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
import scoreboard_web

root = Path(__file__).parent
tree = ast.parse((root / 'scoreboard_app.py').read_text(encoding='utf-8'))
outputs = next(ast.literal_eval(node.value) for node in tree.body
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == 'DECKLINK_OUTPUTS'
                   for target in node.targets))
assert list(outputs.values()) == [0, 1, 2, 3]
for name, number in outputs.items():
    runtime = scoreboard_web.ScoreboardWebRuntime.__new__(scoreboard_web.ScoreboardWebRuntime)
    output_factory = Mock()
    runtime.core = SimpleNamespace(DECKLINK_OUTPUTS=outputs,
        VIDEO_EXPORT_PRESETS={'HD 1080i50': {}}, DeckLinkLiveOutput=output_factory)
    with patch.object(scoreboard_web.subprocess, 'run', side_effect=AssertionError('No scans allowed')):
        assert runtime.output_capabilities()['source'] == 'configured'
        runtime.output_capabilities = Mock(side_effect=AssertionError('Start must not scan'))
        runtime.touch_session = Mock(return_value={'id': 'test', 'priority': 1})
        runtime.lock = threading.RLock()
        runtime.sessions = {}
        runtime.live_owner_id = None
        runtime.live_output = None
        runtime.render = Mock(return_value=(Mock(size=(1920, 1080)), {}))
        runtime._clear_frame = Mock(return_value='black frame')
        runtime.live_status = Mock(return_value={'active': True})
        runtime.start_live('t1', {}, 'HD 1080i50', name, 'test', '127.0.0.1', standby=True)
        output_factory.assert_called_once_with('HD 1080i50', number)
        output_factory.return_value.start.assert_called_once_with('black frame')
        try:
            runtime.start_live('t1', {}, 'HD 1080i50', 'device 99', 'test', '127.0.0.1')
            raise AssertionError('Invalid device accepted')
        except ValueError:
            pass
print('PASS: device IDs 0-3 map directly to output; no discovery; invalid IDs rejected')
