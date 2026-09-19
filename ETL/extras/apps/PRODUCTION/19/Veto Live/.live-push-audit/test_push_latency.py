import copy
import importlib.util
import io
import json
import statistics
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scoreboard_app as core
from scoreboard_web import ProjectConflict, ScoreboardWebRuntime


class HeldOutput:
    def __init__(self):
        self.frame = b'previous'
        self.updates = 0

    def update(self, image):
        self.update_prepared(core.prepare_broadcast_frame(image,'HD 1080i50',preserve_alpha=True).tobytes('raw','BGRA'))

    def update_prepared(self, data):
        self.frame = data
        self.updates += 1

    def poll_error(self):
        return None

    def stop(self):
        pass


def setup_live(runtime):
    runtime.register_session('operator','Operator','127.0.0.1')
    runtime.live_output = HeldOutput()
    runtime.live_owner_id = 'operator'
    runtime.live_preset = 'HD 1080i50'
    runtime.live_output_name = next(iter(core.DECKLINK_OUTPUTS))
    runtime.live_clear_mode = 'external-key'
    return runtime.live_output


class PushLatencyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.runtime = ScoreboardWebRuntime(core,Path(self.directory.name)/'uploads')
        self.output = setup_live(self.runtime)

    def tearDown(self):
        self.runtime.stop_live(force=True)
        self.directory.cleanup()

    def push(self, template='t18', config=None):
        return self.runtime.show_live(template,config or core.DEFAULT_CONFIGS[template],
            'operator','127.0.0.1',self.runtime.program_revision)

    def test_preview_is_reused_and_each_push_publishes_one_complete_frame(self):
        cfg = copy.deepcopy(core.DEFAULT_CONFIGS['t18'])
        with patch.dict(core.RENDERERS,{'t18':core.RENDERERS['t18']}) as renderers:
            renderer = renderers['t18']
            with patch.dict(core.RENDERERS,{'t18':Mock(wraps=renderer)}):
                image,_ = self.runtime.render('t18',cfg,update_live=False)
                image.paste((255,0,255,255),(0,0,image.width,image.height))
                cfg['_web_text_role'] = 'player_b'
                cfg.setdefault('text_styles',{})['player_b'] = {}
                self.push(config=cfg)
                self.assertEqual(core.RENDERERS['t18'].call_count,1)
        self.assertEqual(self.output.updates,1)
        self.assertEqual(len(self.output.frame),1920*1080*4)
        self.assertEqual(self.output.frame[:4],bytes(4))

    def test_cold_render_does_not_block_status_and_cannot_overwrite_new_revision(self):
        entered,release = threading.Event(),threading.Event()
        errors = []
        def render(cfg):
            entered.set()
            self.assertTrue(release.wait(3))
            return core.Image.new('RGBA',(1920,1080),'red')
        def push():
            try:
                self.push()
            except Exception as exc:
                errors.append(exc)
        with patch.dict(core.RENDERERS,{'t18':render}):
            worker = threading.Thread(target=push)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.runtime.live_status('operator','127.0.0.1')['active'])
                self.runtime.clear_live('operator','127.0.0.1',self.runtime.program_revision)
                cleared = self.output.frame
            finally:
                release.set()
                worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],ProjectConflict)
        self.assertIs(self.output.frame,cleared)

    def test_failed_render_holds_existing_frame(self):
        before = self.output.frame
        with patch.dict(core.RENDERERS,{'t18':Mock(side_effect=ValueError('bad graphic'))}):
            with self.assertRaises(ValueError):
                self.push()
        self.assertIs(self.output.frame,before)
        self.assertEqual(self.output.updates,0)

    def test_operator_permission_is_rechecked_after_preparation(self):
        before = self.output.frame
        def render(config):
            self.runtime.sessions['operator']['priority'] = 0
            return core.Image.new('RGBA',(1920,1080),'red')
        with patch.dict(core.RENDERERS,{'t18':render}):
            with self.assertRaises(ProjectConflict):
                self.push()
        self.assertIs(self.output.frame,before)
        self.assertEqual(self.output.updates,0)

    def test_overlay_preview_prepares_fixed_key_output(self):
        cfg = dict(core.DEFAULT_CONFIGS['t18'],transparent_background=False)
        renderer = Mock(wraps=core.RENDERERS['t18'])
        with patch.dict(core.RENDERERS,{'t18':renderer}):
            image,_ = self.runtime.render('t18',cfg,update_live=False,output_mode='external-key')
            self.assertEqual(image.getpixel((0,0))[3],0)
            self.push(config=cfg)
        self.assertEqual(renderer.call_count,1)
        self.assertEqual(self.output.frame[:4],bytes(4))

    def test_static_monitor_uses_broadcast_framing_and_caches_jpeg(self):
        self.runtime.program_frame = core.Image.new('RGBA',(500,500),'red')
        first,revision = self.runtime.program_preview()
        with core.Image.open(io.BytesIO(first)) as image:
            self.assertEqual(image.size,(640,360))
            self.assertLess(image.getpixel((0,0))[0],100)
            self.assertGreater(image.getpixel((320,180))[0],240)
        second,next_revision = self.runtime.program_preview()
        self.assertIs(first,second)
        self.assertEqual(revision,next_revision)

    def test_monitor_is_available_before_output_has_ever_started(self):
        self.runtime.stop_live(force=True)
        del self.runtime.live_clear_mode
        data,_ = self.runtime.program_preview()
        with core.Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size,(640,360))
            self.assertEqual(image.getpixel((320,180)),(0,0,0))

    def test_failed_video_start_holds_poster_and_commits_matching_status(self):
        playback = Mock(error=None,finished=False)
        playback.start.side_effect = RuntimeError('cannot start thread')
        cfg = dict(core.DEFAULT_CONFIGS['t8'],media_path='test.mp4',media_kind='video')
        previous_revision = self.runtime.program_revision
        with patch.object(self.runtime,'normalized_config',return_value=cfg), \
                patch.dict(core.RENDERERS,{'t8':lambda config: core.Image.new('RGBA',(1920,1080),'red')}), \
                patch.object(self.runtime.media,'VideoPlayback',return_value=playback):
            status = self.push('t8',cfg)
        self.assertNotEqual(status['program_revision'],previous_revision)
        self.assertTrue(status['media_finished'])
        self.assertFalse(status['program_dynamic'])
        self.assertIn('poster is held',status['media_error'])
        self.assertEqual(self.output.frame[:4],bytes((0,0,255,255)))

    def test_asset_revision_invalidates_cached_frame(self):
        path = self.runtime.upload_dir/'band.png'
        core.Image.new('RGBA',(30,15),'red').save(path)
        cfg = dict(core.DEFAULT_CONFIGS['t15'],band_path=str(path))
        self.runtime.render('t15',cfg,update_live=False)
        self.push('t15',cfg)
        before = self.output.frame
        core.Image.new('RGBA',(45,20),'blue').save(path)
        self.push('t15',cfg)
        self.assertNotEqual(self.output.frame,before)

    def test_cache_is_bounded(self):
        self.runtime._frame_cache_limit = 20*1024*1024
        for index in range(6):
            cfg = dict(core.DEFAULT_CONFIGS['t18'],player_a=str(index))
            self.runtime.render('t18',cfg,update_live=False)
        self.assertLessEqual(self.runtime._frame_cache_bytes,self.runtime._frame_cache_limit)
        self.assertLessEqual(len(self.runtime._frame_cache),1)


def benchmark():
    spec = importlib.util.spec_from_file_location('baseline_web',Path(__file__).with_name('baseline_web.py'))
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    measurements = {}
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
        for label,klass in [('before',baseline.ScoreboardWebRuntime),('after',ScoreboardWebRuntime)]:
            runtime = klass(core,Path(directory)/label/'uploads')
            setup_live(runtime)
            for template in ('t12','t18'):
                config = copy.deepcopy(core.DEFAULT_CONFIGS[template])
                runtime.render(template,config,update_live=False)
                durations = []
                for _ in range(15):
                    start = time.perf_counter()
                    runtime.show_live(template,config,'operator','127.0.0.1',runtime.program_revision)
                    durations.append((time.perf_counter()-start)*1000)
                measurements[label+'_'+template] = {'median_ms':round(statistics.median(durations),2),
                    'max_ms':round(max(durations),2),'samples':len(durations)}
            runtime.stop_live(force=True)
    print(json.dumps(measurements,indent=2))


if __name__=='__main__':
    if '--benchmark' in __import__('sys').argv:
        benchmark()
    else:
        unittest.main()
