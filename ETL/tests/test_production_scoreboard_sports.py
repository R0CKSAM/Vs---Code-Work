"""Smoke checks for the first cricket and weightlifting live overlays."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / 'extras' / 'apps' / 'PRODUCTION' / 'Veto OTT'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_module('production_scoreboard_app_sports', APP / 'scoreboard_app.py')
web = load_module('production_scoreboard_web_sports', APP / 'scoreboard_web.py')


class SportOverlayTests(unittest.TestCase):
    def setUp(self):
        self.runtime = object.__new__(web.ScoreboardWebRuntime)
        self.runtime.core = core
        self.runtime.app_dir = APP

    def test_categories_keep_tennis_layouts_out(self):
        bootstrap = self.runtime.bootstrap()
        self.assertEqual(bootstrap['competition_templates']['cricket'], ['c1'])
        self.assertEqual(bootstrap['competition_templates']['weightlifting'], ['w1'])
        self.assertNotIn('c1', bootstrap['competition_templates']['davis-cup'])
        self.assertNotIn('w1', bootstrap['competition_templates']['billie-jean-king-cup'])
        with self.assertRaisesRegex(ValueError, 'not available'):
            self.runtime.normalized_config('t1', {}, 'cricket')
        with self.assertRaisesRegex(ValueError, 'not available'):
            self.runtime.normalized_config('c1', {}, 'weightlifting')

    def test_cricket_overs_are_balls_not_decimal_fractions(self):
        config = self.runtime.normalized_config('c1', {'overs':'19.5'}, 'cricket')
        self.assertEqual(config['overs'], '19.5')
        with self.assertRaisesRegex(ValueError, 'cricket notation'):
            self.runtime.normalized_config('c1', {'overs':'19.6'}, 'cricket')

    def test_both_overlays_fit_broadcast_canvas_without_uploaded_images(self):
        for sport, key in [('cricket','c1'), ('weightlifting','w1')]:
            with self.subTest(sport=sport):
                config = self.runtime.normalized_config(key, {}, sport)
                image = core.RENDERERS[key](config)
                self.assertEqual(image.size, (1920,1080))
                self.assertEqual(image.mode, 'RGBA')
                left,top,right,bottom = image.getchannel('A').getbbox()
                self.assertGreaterEqual(left, 48)
                self.assertGreaterEqual(top, 700)
                self.assertLessEqual(right, 1872)
                self.assertLessEqual(bottom, 1032)

    def test_unfittable_name_fails_preview_instead_of_overflowing(self):
        config = self.runtime.normalized_config('w1', {'athlete_name':'Very Long Athlete Name '*12}, 'weightlifting')
        with self.assertRaisesRegex(ValueError, 'too long'):
            core.RENDERERS['w1'](config)

    def test_saved_sport_presets_remain_separate_after_restart(self):
        temp_base = APP.parents[3] / 'output' / 'temp'
        with tempfile.TemporaryDirectory(dir=temp_base) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(temp_base.resolve()))
            uploads = Path(folder) / 'uploads'
            runtime = web.ScoreboardWebRuntime(core, uploads)
            runtime.save_template(dict(competition='cricket', template='c1',
                                       player='Opening match', country='', config={}), '127.0.0.1')
            runtime.save_template(dict(competition='weightlifting', template='w1',
                                       player='Athlete A', country='', config={}), '127.0.0.1')
            reopened = web.ScoreboardWebRuntime(core, uploads)
            self.assertEqual([item['template'] for item in reopened.list_templates('cricket')], ['c1'])
            self.assertEqual([item['template'] for item in reopened.list_templates('weightlifting')], ['w1'])
            self.assertFalse(reopened.list_templates('davis-cup'))


if __name__ == '__main__':
    unittest.main()
