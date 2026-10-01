"""Smoke checks for the cricket and weightlifting live overlays."""

import importlib.util
import base64
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image


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
        self.assertEqual(bootstrap['competition_templates']['cricket'], ['c1', 'c2'])
        self.assertEqual(bootstrap['competition_templates']['weightlifting'], ['w1', 'w2'])
        self.assertFalse(set(core.SPORT_TEMPLATE_KEYS) & set(bootstrap['competition_templates']['davis-cup']))
        self.assertFalse(set(core.SPORT_TEMPLATE_KEYS) & set(bootstrap['competition_templates']['billie-jean-king-cup']))
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
        for sport, key in [('cricket','c1'), ('cricket','c2'),
                           ('weightlifting','w1'), ('weightlifting','w2')]:
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
        for sport, key, field in [('cricket','c2','player_name'),
                                  ('weightlifting','w1','athlete_name'),
                                  ('weightlifting','w2','athlete_name')]:
            with self.subTest(key=key):
                config = self.runtime.normalized_config(key, {field:'Very Long Athlete Name '*12}, sport)
                with self.assertRaisesRegex(ValueError, 'too long'):
                    core.RENDERERS[key](config)

    def test_result_total_is_derived_and_zero_means_unreported(self):
        config = self.runtime.normalized_config('w2',
            {'snatch_kg':100, 'clean_jerk_kg':120, 'total_kg':999}, 'weightlifting')
        self.assertNotIn('total_kg', config)
        self.assertEqual(config['snatch_kg'] + config['clean_jerk_kg'], 220)
        self.assertEqual(config['placement'], '')
        empty = self.runtime.normalized_config('w2', {'snatch_kg':0}, 'weightlifting')
        self.assertEqual(empty['clean_jerk_kg'], 0)

    def test_uploaded_portrait_and_logo_render_inside_both_new_graphics(self):
        temp_base = APP.parents[3] / 'output' / 'temp'
        with tempfile.TemporaryDirectory(dir=temp_base) as folder:
            uploads = Path(folder) / 'uploads'
            runtime = web.ScoreboardWebRuntime(core, uploads)
            source = Image.new('RGB', (300, 300), (220, 35, 45))
            buffer = io.BytesIO()
            source.save(buffer, 'PNG')
            data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
            path = runtime.upload({'name':'test.png','data':data})['path']
            for sport, key, logo_field, logo_y in [('cricket','c2','team_logo_path',940),
                                                   ('weightlifting','w2','country_logo_path',910)]:
                with self.subTest(key=key):
                    config = runtime.normalized_config(key,
                        {'photo_path':path, logo_field:path}, sport)
                    image = core.RENDERERS[key](config)
                    self.assertEqual(image.getpixel((180, 875))[:3], (220, 35, 45))
                    self.assertEqual(image.getpixel((350, logo_y))[:3], (220, 35, 45))

    def test_saved_sport_presets_remain_separate_after_restart(self):
        temp_base = APP.parents[3] / 'output' / 'temp'
        with tempfile.TemporaryDirectory(dir=temp_base) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(temp_base.resolve()))
            uploads = Path(folder) / 'uploads'
            runtime = web.ScoreboardWebRuntime(core, uploads)
            runtime.save_template(dict(competition='cricket', template='c1',
                                       player='Opening match', country='', config={}), '127.0.0.1')
            runtime.save_template(dict(competition='cricket', template='c2',
                                       player='Player A', country='', config={}), '127.0.0.1')
            runtime.save_template(dict(competition='weightlifting', template='w1',
                                       player='Athlete A', country='', config={}), '127.0.0.1')
            runtime.save_template(dict(competition='weightlifting', template='w2',
                                       player='Athlete result', country='', config={}), '127.0.0.1')
            reopened = web.ScoreboardWebRuntime(core, uploads)
            self.assertEqual({item['template'] for item in reopened.list_templates('cricket')}, {'c1','c2'})
            self.assertEqual({item['template'] for item in reopened.list_templates('weightlifting')}, {'w1','w2'})
            self.assertFalse(reopened.list_templates('davis-cup'))


if __name__ == '__main__':
    unittest.main()
