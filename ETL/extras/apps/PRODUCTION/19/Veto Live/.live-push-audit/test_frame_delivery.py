import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import scoreboard_app as core


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def perf_counter(self):
        return self.now


class FrameDeliveryTests(unittest.TestCase):
    def make_output(self, preset="HD 1080i50"):
        output = core.DeckLinkLiveOutput.__new__(core.DeckLinkLiveOutput)
        output.preset_name = preset
        output.external_key = True
        output.running = True
        output._frame_lock = threading.Lock()
        output._frame_data = b""
        output._thread_error = None
        return output

    def test_prepared_frame_keeps_color_and_alpha_and_rejects_invalid_update(self):
        output = self.make_output()
        frame = Image.new("RGBA", (1920, 1080), (17, 49, 91, 0))
        frame.putpixel((30, 20), (41, 81, 123, 127))
        data = output.prepare_frame(frame)
        output.update_prepared(data)
        self.assertIs(output._frame_data, data)
        self.assertEqual(output.snapshot_frame().tobytes(), frame.tobytes())
        for invalid in (b"bad", bytearray(data)):
            with self.assertRaises(ValueError):
                output.update_prepared(invalid)
            self.assertIs(output._frame_data, data)

    def test_packing_leaves_previous_frame_available_to_feeder(self):
        output = self.make_output()
        output._frame_data = b"previous complete frame"

        def pack(image, preset):
            acquired = output._frame_lock.acquire(blocking=False)
            self.assertTrue(acquired, "Packing must not block the frame feeder")
            try:
                self.assertEqual(output._frame_data, b"previous complete frame")
            finally:
                if acquired:
                    output._frame_lock.release()
            return b"new complete frame"

        with patch.object(core, "prepare_decklink_frame", side_effect=pack):
            output._set_frame(None)
        self.assertEqual(output._frame_data, b"new complete frame")

    def feed(self, preset="HD 1080i50", first_push_delay=0, error=None):
        output = self.make_output(preset)
        clock = FakeClock()
        sent = []
        waits = []

        def push(signal, buffer):
            if error:
                raise error
            sent.append(buffer)
            if len(sent) == 1:
                clock.now += first_push_delay
            return "ok"

        def wait(delay):
            waits.append(delay)
            clock.now += delay

        output.Gst = SimpleNamespace(
            SECOND=1_000_000_000,
            Buffer=SimpleNamespace(new_wrapped=lambda data: SimpleNamespace(
                copy_region=lambda flags, offset, size: SimpleNamespace(data=data))),
            BufferCopyFlags=SimpleNamespace(MEMORY=1),
            FlowReturn=SimpleNamespace(OK="ok"),
        )
        output.source = SimpleNamespace(emit=push)
        output._stop_event = SimpleNamespace(is_set=lambda: len(sent) >= 4, wait=wait)
        with patch.object(core.time, "perf_counter", clock.perf_counter):
            output._feed_frames()
        return output, sent, waits

    def test_stall_skips_expired_slots_instead_of_catchup_burst(self):
        output, sent, waits = self.feed(first_push_delay=0.23)
        self.assertIsNone(output._thread_error)
        self.assertEqual([buffer.pts for buffer in sent], [0, 200_000_000, 240_000_000, 280_000_000])
        self.assertEqual([buffer.duration for buffer in sent], [40_000_000] * 4)
        self.assertGreater(waits[1], 0)

    def test_fractional_frame_rate_uses_exact_rational_timestamps(self):
        _, sent, _ = self.feed("HD 1080p29.97")
        self.assertEqual([buffer.pts for buffer in sent], [0, 33_366_666, 66_733_333, 100_100_000])
        self.assertEqual([buffer.duration for buffer in sent], [33_366_666, 33_366_667, 33_366_667, 33_366_666])

    def test_feeder_exceptions_are_reported(self):
        output, _, _ = self.feed(error=RuntimeError("test failure"))
        self.assertIn("test failure", output._thread_error)


if __name__ == "__main__":
    unittest.main()
