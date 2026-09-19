import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scoreboard_app as core
from scoreboard_web import OVERLAY_TEMPLATES, ScoreboardWebRuntime
from test_alpha_output import MemoryOutput


class CustomBandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent, ignore_cleanup_errors=True)
        self.runtime = ScoreboardWebRuntime(core, Path(self.directory.name) / 'uploads')
        self.band = self.runtime.upload_dir / 'band.png'
        source = core.Image.new('RGBA',(1200,300),(0,0,0,0))
        core.Image.new('RGBA',(1000,180),(0,110,60,255)).save(self.band)
        self.client,self.address='custom-band-test','127.0.0.1'
        self.runtime.register_session(self.client,'Custom band test',self.address)

    def tearDown(self):
        self.runtime.stop_live(force=True)
        self.directory.cleanup()

    def config(self):
        config=copy.deepcopy(core.DEFAULT_CONFIGS['t15'])
        config['band_path']=str(self.band)
        return config

    def test_alpha_and_magenta_rendering(self):
        self.assertIn('t15',OVERLAY_TEMPLATES)
        alpha,_=self.runtime.render('t15',self.config(),output_mode='external-key')
        self.assertEqual(alpha.mode,'RGBA')
        self.assertEqual(alpha.getchannel('A').getextrema(),(0,255))
        magenta,_=self.runtime.render('t15',self.config(),output_mode='chroma-magenta')
        self.assertEqual(magenta.mode,'RGB')
        self.assertEqual(magenta.getpixel((0,0)),(255,0,255))

    def test_move_resize_without_pipeline_restart(self):
        with patch.object(core,'DeckLinkLiveOutput',MemoryOutput):
            output_name=next(iter(core.DECKLINK_KEY_PAIRS))
            self.runtime.start_live('t15',self.config(),'HD 1080i50',output_name,
                                    self.client,self.address,standby=True,
                                    clear_mode='external-key',keyer_confirmed=True)
            output=self.runtime.live_output
            config=self.config();config.update(band_x_pct=35,band_y_pct=62,band_size_pct=125)
            self.runtime.show_live('t15',config,self.client,self.address,
                                   expected_revision=self.runtime.program_revision)
            self.assertIs(self.runtime.live_output,output)
            self.assertTrue(output.running)


if __name__=='__main__':
    unittest.main()
