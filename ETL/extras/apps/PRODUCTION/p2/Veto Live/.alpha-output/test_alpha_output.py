import copy
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime


class MemoryOutput:
    def __init__(self, preset, device, external_key=False):
        self.preset_name = preset
        self.device_number = device
        self.external_key = external_key
        self.running = False
        self._frame_lock = threading.Lock()
        self._frame_data = b''

    _set_frame = core.DeckLinkLiveOutput._set_frame
    snapshot_frame = core.DeckLinkLiveOutput.snapshot_frame

    def start(self, image):
        self.running = True
        self._set_frame(image)

    def update(self, image):
        self._set_frame(image)

    def stop(self):
        self.running = False

    def poll_error(self):
        return None


class AlphaTests(unittest.TestCase):
    def test_render_masks_and_opacity(self):
        for key in ('t5', 't11'):
            cfg = copy.deepcopy(core.DEFAULT_CONFIGS[key])
            cfg['transparent_background'] = True
            for opacity, maximum in ((100, 255), (50, 128), (0, 0)):
                cfg['overlay_opacity_pct'] = opacity
                image = core.RENDERERS[key](cfg)
                self.assertEqual(image.mode, 'RGBA')
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getchannel('A').getextrema(), (0, maximum))
            cfg['transparent_background'] = False
            opaque = core.RENDERERS[key](cfg).convert('RGBA')
            self.assertEqual(opaque.getchannel('A').getextrema(), (255, 255))

    def test_frame_padding_and_snapshot(self):
        src = core.Image.new('RGBA', (100, 100), (10, 20, 30, 128))
        output = MemoryOutput('HD 1080i50', 0, True)
        output.start(src)
        frame = output.snapshot_frame()
        self.assertEqual(frame.size, (1920, 1080))
        self.assertEqual(frame.getpixel((0, 0)), (0, 0, 0, 0))
        center = frame.getpixel((960, 540))
        self.assertEqual(center[3], 128)
        self.assertTrue(all(abs(actual - expected) <= 1 for actual, expected in zip(center[:3], (10, 20, 30))))

    def test_runtime_no_scanning_and_transparent_clear(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            runtime = ScoreboardWebRuntime(core, Path(directory) / 'uploads')
            client, address = 'alpha-test-operator', '127.0.0.1'
            runtime.register_session(client, 'Alpha test', address)
            output_name = next(iter(core.DECKLINK_KEY_PAIRS))
            cfg = dict(core.DEFAULT_CONFIGS['t5'], transparent_background=False)
            with patch.object(core, 'DeckLinkLiveOutput', MemoryOutput), patch.object(
                runtime, 'output_capabilities', side_effect=AssertionError('No scans allowed')
            ):
                for bad in ({'template': 't1'}, {'preset': 'HD 1080p25'},
                            {'output_name': list(core.DECKLINK_OUTPUTS)[2]}, {'keyer_confirmed': False}):
                    args = dict(template='t5', config=cfg, preset='HD 1080i50',
                                output_name=output_name, client_id=client, remote_address=address,
                                standby=True, clear_mode='external-key', keyer_confirmed=True)
                    args.update(bad)
                    with self.assertRaises(ValueError):
                        runtime.start_live(**args)
                    self.assertIsNone(runtime.live_output)
                runtime.start_live('t5', cfg, 'HD 1080i50', output_name, client, address,
                                   standby=True, clear_mode='external-key', keyer_confirmed=True)
                self.assertTrue(runtime.live_output.external_key)
                self.assertEqual(runtime.live_output.snapshot_frame().getchannel('A').getextrema(), (0, 0))
                for key in ('t5', 't11'):
                    cfg = dict(core.DEFAULT_CONFIGS[key], transparent_background=False)
                    runtime.show_live(key, cfg, client, address)
                    self.assertEqual(runtime.live_output.snapshot_frame().getchannel('A').getextrema(), (0, 255))
                    self.assertFalse(cfg['transparent_background'])
                    data, revision = runtime.program_preview()
                    self.assertEqual(core.Image.open(io.BytesIO(data)).format, 'JPEG')
                    self.assertEqual(revision, runtime.program_revision)
                with self.assertRaises(ValueError):
                    runtime.show_live('t1', core.DEFAULT_CONFIGS['t1'], client, address)
                runtime.clear_live(client, address)
                self.assertEqual(runtime.live_output.snapshot_frame().getchannel('A').getextrema(), (0, 0))
                runtime.stop_live(force=True)
                for name, device in core.DECKLINK_OUTPUTS.items():
                    runtime.start_live('t5', cfg, 'HD 1080i50', name, client, address, standby=True)
                    self.assertFalse(runtime.live_output.external_key)
                    self.assertEqual(runtime.live_output.device_number, device)
                    self.assertEqual(runtime.live_output.snapshot_frame().mode, 'RGB')
                    runtime.stop_live(force=True)

    def test_1080i50_software_pipeline_preserves_alpha(self):
        Gst = core.load_gstreamer()
        description = core.build_decklink_pipeline('HD 1080i50', 0, True)
        self.assertIn('duplex-mode=full', description)
        self.assertIn('keyer-mode=external', description)
        self.assertIn('video-format=8bit-bgra', description)
        # Replace the hardware sink so this test never claims an SDI connector.
        description = description.rsplit(' ! decklinkvideosink', 1)[0]
        pipeline = Gst.parse_launch(description + ' ! appsink name=result sync=false')
        source = pipeline.get_by_name('scoreboard_source')
        sink = pipeline.get_by_name('result')
        frame = core.Image.new('RGBA', (1920, 1080), (90, 180, 40, 0))
        frame.paste((90, 180, 40, 128), (640, 0, 1280, 1080))
        frame.paste((90, 180, 40, 255), (1280, 0, 1920, 1080))
        try:
            self.assertNotEqual(pipeline.set_state(Gst.State.PLAYING), Gst.StateChangeReturn.FAILURE)
            for index in range(4):
                buffer = Gst.Buffer.new_wrapped(frame.tobytes('raw', 'BGRA'))
                buffer.pts = index * Gst.SECOND // 25
                buffer.duration = Gst.SECOND // 25
                self.assertEqual(source.emit('push-buffer', buffer), Gst.FlowReturn.OK)
                time.sleep(.05)
            sample = sink.emit('try-pull-sample', 3 * Gst.SECOND)
            if sample is None:
                error = pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
                self.fail(str(error.parse_error()) if error else 'No software output frame')
            caps = sample.get_caps().get_structure(0)
            self.assertEqual(caps.get_string('format'), 'BGRA')
            self.assertEqual(caps.get_string('interlace-mode'), 'interleaved')
            data = sample.get_buffer().extract_dup(0, 1920 * 1080 * 4)
            decoded = core.Image.frombytes('RGBA', (1920, 1080), data, 'raw', 'BGRA')
            for x, alpha in ((100, 0), (900, 128), (1600, 255)):
                for y in (100, 101, 500, 501):
                    self.assertEqual(decoded.getpixel((x, y))[3], alpha)
        finally:
            pipeline.set_state(Gst.State.NULL)


if __name__ == '__main__':
    import faulthandler
    faulthandler.dump_traceback_later(20, exit=True)
    unittest.main(verbosity=2)
