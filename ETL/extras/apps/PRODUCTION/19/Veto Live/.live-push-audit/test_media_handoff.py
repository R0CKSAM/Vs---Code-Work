import io
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import scoreboard_media as media


class Process:
    def __init__(self, data=b''):
        self.stdout = io.BytesIO(data)
        self.terminated = threading.Event()
        self.allow_cleanup = threading.Event()
        self.allow_cleanup.set()

    def poll(self):
        return 0 if self.terminated.is_set() else None

    def terminate(self):
        self.allow_cleanup.wait(2)
        self.terminated.set()

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated.set()


def core_for(convert):
    return SimpleNamespace(
        locate_ffmpeg=lambda: 'test-ffmpeg',
        VIDEO_EXPORT_PRESETS={'test': {'width': 1, 'height': 1, 'fps': 25}},
        render_custom_text_overlay=lambda config, size: SimpleNamespace(getbbox=lambda: None),
        Image=SimpleNamespace(frombytes=convert),
    )


class MediaHandoffTests(unittest.TestCase):
    def test_slow_decoder_cleanup_does_not_block_retirement(self):
        process = Process()
        process.allow_cleanup.clear()
        with patch.object(media.subprocess, 'Popen', return_value=process):
            playback = media.VideoPlayback(core_for(lambda *args: 'frame'), None, 'test', 'test')
        retired = threading.Event()
        worker = threading.Thread(target=lambda: (playback.request_stop(), retired.set()))
        worker.start()
        try:
            self.assertTrue(retired.wait(0.5))
            self.assertTrue(playback.stopping.is_set())
            self.assertFalse(process.terminated.is_set())
        finally:
            process.allow_cleanup.set()
            worker.join(2)
            playback.stop()
        self.assertTrue(process.stdout.closed)

    def test_frame_being_composed_cannot_overwrite_next_program(self):
        entered, resume = threading.Event(), threading.Event()
        frames = []

        def convert(*args):
            entered.set()
            resume.wait(2)
            return 'old video'

        with patch.object(media.subprocess, 'Popen', return_value=Process(b'123')):
            playback = media.VideoPlayback(core_for(convert), SimpleNamespace(update=frames.append), 'test', 'test')
        playback.start()
        try:
            self.assertTrue(entered.wait(1))
            playback.request_stop()
            frames.append('new program')
        finally:
            resume.set()
            playback.stop()
        self.assertEqual(frames, ['new program'])

    def test_fixed_cadence_accounts_for_frame_processing_time(self):
        clock = [0.0]
        shown = []

        class ClockEvent:
            stopped = False

            def is_set(self):
                return self.stopped

            def set(self):
                self.stopped = True

            def wait(self, duration):
                clock[0] += duration
                return self.stopped

        def convert(*args):
            clock[0] += 0.010
            return 'frame'

        def update(image):
            shown.append(clock[0])
            clock[0] += 0.005

        with patch.object(media.subprocess, 'Popen', return_value=Process(b'123' * 3)):
            playback = media.VideoPlayback(core_for(convert), SimpleNamespace(update=update), 'test', 'test')
        playback.stopping = ClockEvent()
        with patch.object(media.time, 'monotonic', side_effect=lambda: clock[0]):
            playback._run()
            playback.stop()
        self.assertEqual(len(shown), 3)
        self.assertAlmostEqual(shown[1] - shown[0], 0.040)
        self.assertAlmostEqual(shown[2] - shown[1], 0.040)

    def test_frame_packing_does_not_delay_cancellation(self):
        packing, resume, retired = threading.Event(), threading.Event(), threading.Event()
        published = []

        def prepare(image):
            packing.set()
            resume.wait(2)
            return b'prepared'

        output = SimpleNamespace(prepare_frame=prepare, update_prepared=published.append)
        with patch.object(media.subprocess, 'Popen', return_value=Process(b'123')):
            playback = media.VideoPlayback(core_for(lambda *args: 'frame'), output, 'test', 'test')
        playback.start()
        worker = threading.Thread(target=lambda: (playback.request_stop(), retired.set()))
        try:
            self.assertTrue(packing.wait(1))
            worker.start()
            self.assertTrue(retired.wait(0.5))
            published.append(b'next-program')
        finally:
            resume.set()
            if worker.is_alive():
                worker.join(2)
            playback.stop()
        self.assertEqual(published, [b'next-program'])

    def test_delayed_frame_is_not_immediately_replaced_by_catchup(self):
        clock = [0.0]
        shown = []
        costs = iter((0.010, 0.110, 0.010, 0.010))

        class ClockEvent:
            stopped = False

            def is_set(self):
                return self.stopped

            def set(self):
                self.stopped = True

            def wait(self, duration):
                clock[0] += duration
                return self.stopped

        def convert(*args):
            clock[0] += next(costs)
            return 'frame'

        output = SimpleNamespace(update=lambda image: shown.append(clock[0]))
        with patch.object(media.subprocess, 'Popen', return_value=Process(b'123' * 4)):
            playback = media.VideoPlayback(core_for(convert), output, 'test', 'test')
        playback.stopping = ClockEvent()
        with patch.object(media.time, 'monotonic', side_effect=lambda: clock[0]):
            playback._run()
            playback.stop()
        self.assertEqual(len(shown), 4)
        self.assertGreater(shown[1] - shown[0], 0.100)
        self.assertAlmostEqual(shown[2] - shown[1], 0.040)
        self.assertAlmostEqual(shown[3] - shown[2], 0.040)


if __name__ == '__main__':
    unittest.main(verbosity=2)
