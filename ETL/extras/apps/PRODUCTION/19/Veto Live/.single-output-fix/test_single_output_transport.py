import time
import unittest

import scoreboard_app as core


class SingleOutputTransportTests(unittest.TestCase):
    def test_single_port_uses_known_working_bgra_transport(self):
        description=core.build_decklink_pipeline('HD 1080i50',0,False,True)
        self.assertIn('format=BGRA',description)
        self.assertIn('format=AYUV',description)
        self.assertIn('video-format=8bit-bgra',description)
        self.assertIn('keyer-mode=off',description)
        self.assertIn('profile=two-sub-devices-half',description)
        self.assertNotIn('format=UYVY',description)

    def test_software_path_negotiates_interlaced_bgra(self):
        Gst=core.load_gstreamer()
        description=core.build_decklink_pipeline('HD 1080i50',0,False,True)
        description=description.rsplit(' ! decklinkvideosink',1)[0]
        pipeline=Gst.parse_launch(description+' ! appsink name=result sync=false')
        source=pipeline.get_by_name('scoreboard_source');sink=pipeline.get_by_name('result')
        frame=core.Image.new('RGBA',(1920,1080),(255,0,255,255))
        try:
            self.assertNotEqual(pipeline.set_state(Gst.State.PLAYING),Gst.StateChangeReturn.FAILURE)
            for index in range(4):
                buffer=Gst.Buffer.new_wrapped(frame.tobytes('raw','BGRA'))
                buffer.pts=index*Gst.SECOND//25;buffer.duration=Gst.SECOND//25
                self.assertEqual(source.emit('push-buffer',buffer),Gst.FlowReturn.OK)
                time.sleep(.05)
            sample=sink.emit('try-pull-sample',3*Gst.SECOND)
            if sample is None:
                error=pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
                self.fail(str(error.parse_error()) if error else 'No negotiated frame')
            caps=sample.get_caps().get_structure(0)
            self.assertEqual(caps.get_string('format'),'BGRA')
            self.assertEqual(caps.get_string('interlace-mode'),'interleaved')
        finally:
            pipeline.set_state(Gst.State.NULL)


if __name__=='__main__':
    unittest.main()
