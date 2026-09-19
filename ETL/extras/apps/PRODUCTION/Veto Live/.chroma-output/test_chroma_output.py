import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scoreboard_app as core
from scoreboard_web import CHROMA_COLORS, ScoreboardWebRuntime
from test_alpha_output import MemoryOutput


class ChromaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.runtime = ScoreboardWebRuntime(core, Path(self.directory.name) / 'uploads')
        self.client = 'chroma-test-operator'
        self.address = '127.0.0.1'
        self.runtime.register_session(self.client, 'Chroma test', self.address)
        self.output_name = next(iter(core.DECKLINK_OUTPUTS))

    def tearDown(self):
        self.runtime.stop_live(force=True)
        self.directory.cleanup()

    def test_both_templates_and_all_chroma_backgrounds(self):
        for template in ('t5', 't11'):
            cfg = dict(core.DEFAULT_CONFIGS[template], transparent_background=False)
            original = copy.deepcopy(cfg)
            alpha, _ = self.runtime.render(template, cfg, update_live=False, output_mode='external-key')
            solid = next((i % alpha.width, i // alpha.width) for i, value in
                         enumerate(alpha.getchannel('A').tobytes()) if value == 255)
            for mode, color in CHROMA_COLORS.items():
                frame, _ = self.runtime.render(template, cfg, update_live=False, output_mode=mode)
                self.assertEqual(frame.mode, 'RGB')
                self.assertEqual(frame.size, (1920, 1080))
                self.assertEqual(frame.getpixel((0, 0)), color)
                self.assertEqual(frame.getpixel(solid), alpha.getpixel(solid)[:3])
                clear = self.runtime._clear_frame(frame.size, mode)
                self.assertEqual(clear.getextrema(), tuple((value, value) for value in color))
            self.assertEqual(cfg, original)

    def test_padding_and_zero_opacity_remain_magenta(self):
        portrait = core.Image.new('RGBA', (100, 200), (10, 90, 20, 255))
        with patch.dict(core.RENDERERS, {'t5': lambda cfg: portrait}):
            frame, _ = self.runtime.render('t5', core.DEFAULT_CONFIGS['t5'], update_live=False,
                                           output_mode='chroma-magenta')
            self.assertEqual(frame.getpixel((0, 0)), (255, 0, 255))
            self.assertEqual(frame.getpixel((1919, 1079)), (255, 0, 255))
            self.assertEqual(frame.getpixel((960, 540)), (10, 90, 20))
        for template in ('t5', 't11'):
            cfg = dict(core.DEFAULT_CONFIGS[template], overlay_opacity_pct=0)
            frame, _ = self.runtime.render(template, cfg, update_live=False, output_mode='chroma-magenta')
            self.assertEqual(frame.getextrema(), ((255, 255), (0, 0), (255, 255)))

    def test_removed_chroma_modes_are_rejected(self):
        self.assertEqual(set(CHROMA_COLORS), {'chroma-magenta'})
        for mode in ('chroma-green', 'chroma-blue'):
            with self.assertRaises(ValueError):
                self.runtime.start_live('t5', core.DEFAULT_CONFIGS['t5'], 'HD 1080i50',
                                        self.output_name, self.client, self.address,
                                        clear_mode=mode, keyer_confirmed=True)
            self.assertIsNone(self.runtime.live_output)

    def test_start_push_clear_and_switch_to_alpha(self):
        runtime = self.runtime
        cfg = dict(core.DEFAULT_CONFIGS['t5'], transparent_background=False)
        with patch.object(core, 'DeckLinkLiveOutput', MemoryOutput), patch.object(
            runtime, 'output_capabilities', side_effect=AssertionError('No scanning')
        ):
            args = dict(template='t5', config=cfg, preset='HD 1080i50', output_name=self.output_name,
                        client_id=self.client, remote_address=self.address, standby=True,
                        clear_mode='chroma-magenta', keyer_confirmed=True)
            for bad in ({'template': 't1'}, {'preset': 'HD 1080p25'}, {'keyer_confirmed': False}):
                with self.assertRaises(ValueError):
                    runtime.start_live(**dict(args, **bad))
                self.assertIsNone(runtime.live_output)
            runtime.start_live(**args)
            self.assertFalse(runtime.live_output.external_key)
            self.assertTrue(runtime.live_output.single_port)
            self.assertEqual(runtime.live_output.snapshot_frame().getextrema(), ((255, 255), (0, 0), (255, 255)))
            for template in ('t5', 't11'):
                runtime.show_live(template, core.DEFAULT_CONFIGS[template], self.client, self.address)
                self.assertEqual(runtime.live_output.snapshot_frame().getpixel((0, 0)), (255, 0, 255))
                self.assertIsNotNone(runtime.on_air)
            before = runtime.live_output.snapshot_frame().tobytes()
            with self.assertRaises(ValueError):
                runtime.show_live('t1', core.DEFAULT_CONFIGS['t1'], self.client, self.address)
            self.assertEqual(before, runtime.live_output.snapshot_frame().tobytes())
            runtime.clear_live(self.client, self.address)
            self.assertEqual(runtime.live_output.snapshot_frame().getextrema(), ((255, 255), (0, 0), (255, 255)))
            previous = runtime.live_output
            runtime.start_live(**dict(args, clear_mode='external-key'))
            self.assertFalse(previous.running)
            self.assertTrue(runtime.live_output.external_key)
            self.assertEqual(runtime.live_output.snapshot_frame().getchannel('A').getextrema(), (0, 0))
            runtime.show_live('t11', core.DEFAULT_CONFIGS['t11'], self.client, self.address)
            self.assertEqual(runtime.live_output.snapshot_frame().getchannel('A').getextrema(), (0, 255))

    def test_installed_sink_accepts_both_pipelines_without_starting_output(self):
        Gst = core.load_gstreamer()
        for external, single, profile in ((True, False, 'one-sub-device-full'),
                                          (False, True, 'two-sub-devices-half')):
            output = core.DeckLinkLiveOutput('HD 1080i50', 0, external_key=external, single_port=single)
            try:
                elements = list(output.pipeline.iterate_elements())
                sink = next(element for element in elements if element.get_factory().get_name() == 'decklinkvideosink')
                self.assertEqual(sink.get_property('profile').value_nick, profile)
                self.assertEqual(sink.get_property('keyer-mode').value_nick, 'external' if external else 'off')
                self.assertEqual(output.pipeline.get_state(0)[1], Gst.State.NULL)
            finally:
                output.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
