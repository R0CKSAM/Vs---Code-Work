import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scoreboard_app as core
from scoreboard_web import OVERLAY_TEMPLATES, ScoreboardWebRuntime
from test_alpha_output import MemoryOutput


class RecordingOutput(MemoryOutput):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frames = []
        self.stop_count = 0
        type(self).instances.append(self)

    def start(self, image):
        super().start(image)
        self.frames.append(self.snapshot_frame())

    def update(self, image):
        super().update(image)
        self.frames.append(self.snapshot_frame())

    def stop(self):
        self.stop_count += 1
        super().stop()


class SmartLiveTests(unittest.TestCase):
    def setUp(self):
        RecordingOutput.instances.clear()
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent, ignore_cleanup_errors=True)
        self.runtime = ScoreboardWebRuntime(core, Path(self.directory.name) / 'uploads')
        self.media_path = self.runtime.upload_dir / 'smart-live-test.png'
        core.Image.new('RGB', (320, 180), (12, 60, 90)).save(self.media_path)
        self.media_path.with_suffix('.media.json').write_text(
            json.dumps({'kind': 'image', 'poster': ''}), encoding='utf-8')
        self.client, self.address = 'smart-live-test', '127.0.0.1'
        self.runtime.register_session(self.client, 'Smart live test', self.address)

    def tearDown(self):
        self.runtime.stop_live(force=True)

    def config(self, template):
        cfg = copy.deepcopy(core.DEFAULT_CONFIGS[template])
        if template == 't8':
            cfg.update(media_kind='image', media_path=str(self.media_path))
        return cfg

    def run_session(self, mode):
        output_name = next(iter(core.DECKLINK_KEY_PAIRS if mode == 'external-key' else core.DECKLINK_OUTPUTS))
        with patch.object(core, 'DeckLinkLiveOutput', RecordingOutput):
            self.runtime.start_live('t1', self.config('t1'), 'HD 1080i50', output_name,
                                    self.client, self.address, standby=True,
                                    clear_mode=mode, keyer_confirmed=True)
            output = self.runtime.live_output
            self.assertEqual(len(RecordingOutput.instances), 1)
            self.assertEqual(len(output.frames), 1)
            for index, template in enumerate(core.WEB_TEMPLATE_KEYS, start=1):
                revision = self.runtime.program_revision
                self.runtime.show_live(template, self.config(template), self.client, self.address,
                                       expected_revision=revision)
                self.assertIs(self.runtime.live_output, output)
                self.assertTrue(output.running)
                self.assertEqual(output.stop_count, 0)
                self.assertEqual(len(output.frames), index + 1)
                self.assertEqual(self.runtime.program_layout,
                                 'overlay' if template in OVERLAY_TEMPLATES else 'full-picture')
                frame = output.frames[-1]
                if mode == 'external-key':
                    expected = (0, 255) if template in OVERLAY_TEMPLATES else (255, 255)
                    self.assertEqual(frame.getchannel('A').getextrema(), expected, template)
                elif template in OVERLAY_TEMPLATES:
                    self.assertEqual(frame.getpixel((0, 0)), (255, 0, 255), template)
                else:
                    self.assertNotEqual(frame.getextrema(), ((255, 255), (0, 0), (255, 255)), template)
            self.assertEqual(len(RecordingOutput.instances), 1)
            self.assertEqual(output.stop_count, 0)

    def test_every_template_switches_without_restarting_alpha_output(self):
        self.run_session('external-key')

    def test_every_template_switches_without_restarting_magenta_output(self):
        self.run_session('chroma-magenta')

    def test_overlay_classification_is_explicit(self):
        self.assertEqual(OVERLAY_TEMPLATES, frozenset(('t5', 't11')))
        self.assertEqual(set(core.WEB_TEMPLATE_KEYS) - OVERLAY_TEMPLATES,
                         {'t1','t2','t3','t4','t6','t7','t8','t9','t10','t12','t13'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
