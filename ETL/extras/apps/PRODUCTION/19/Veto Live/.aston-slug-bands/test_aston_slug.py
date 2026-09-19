import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scoreboard_app as core
from scoreboard_web import OVERLAY_TEMPLATES, ScoreboardWebRuntime
from test_alpha_output import MemoryOutput


class AstonSlugTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir=Path(__file__).parent,ignore_cleanup_errors=True)
        self.runtime=ScoreboardWebRuntime(core,Path(self.directory.name)/'uploads')
        self.client,self.address='text-band-test','127.0.0.1'
        self.runtime.register_session(self.client,'Text band test',self.address)

    def tearDown(self):
        self.runtime.stop_live(force=True)
        self.directory.cleanup()

    def test_unicode_alpha_and_magenta(self):
        values={'t16':{'text_a':'भारत','text_b':'البث المباشر'},'t17':{'text':'라이브 경기'}}
        for key,updates in values.items():
            self.assertIn(key,OVERLAY_TEMPLATES)
            config=copy.deepcopy(core.DEFAULT_CONFIGS[key]);config.update(updates)
            alpha,_=self.runtime.render(key,config,output_mode='external-key')
            self.assertEqual(alpha.mode,'RGBA');self.assertEqual(alpha.getchannel('A').getextrema(),(0,255))
            magenta,_=self.runtime.render(key,config,output_mode='chroma-magenta')
            self.assertEqual(magenta.mode,'RGB');self.assertEqual(magenta.getpixel((0,0)),(255,0,255))

    def test_switch_without_pipeline_restart(self):
        with patch.object(core,'DeckLinkLiveOutput',MemoryOutput):
            output_name=next(iter(core.DECKLINK_KEY_PAIRS))
            self.runtime.start_live('t16',core.DEFAULT_CONFIGS['t16'],'HD 1080i50',output_name,
                                    self.client,self.address,standby=True,
                                    clear_mode='external-key',keyer_confirmed=True)
            output=self.runtime.live_output
            self.runtime.show_live('t16',core.DEFAULT_CONFIGS['t16'],self.client,self.address,
                                   expected_revision=self.runtime.program_revision)
            self.runtime.show_live('t17',core.DEFAULT_CONFIGS['t17'],self.client,self.address,
                                   expected_revision=self.runtime.program_revision)
            self.assertIs(self.runtime.live_output,output)
            self.assertTrue(output.running)


if __name__=='__main__':
    unittest.main()
