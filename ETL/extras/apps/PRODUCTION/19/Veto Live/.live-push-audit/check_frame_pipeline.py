"""Exercise the actual conversion pipeline with an in-memory sink, never SDI."""
import json
import threading

from PIL import Image

import scoreboard_app as core


Gst = core.load_gstreamer()
description = core.build_decklink_pipeline("HD 1080i50", 0, external_key=True)
description = description.rsplit(" ! ", 1)[0] + " ! fakesink name=verify_sink sync=true signal-handoffs=true"
output = core.DeckLinkLiveOutput.__new__(core.DeckLinkLiveOutput)
output.preset_name = "HD 1080i50"
output.device_number = 0
output.external_key = True
output.Gst = Gst
output.pipeline = Gst.parse_launch(description)
output.source = output.pipeline.get_by_name("scoreboard_source")
output.bus = output.pipeline.get_bus()
output.running = False
output._frame_lock = threading.Lock()
output._frame_data = b""
output._stop_event = threading.Event()
output._thread = None
output._thread_error = None
samples = []
first = threading.Event()
second = threading.Event()


def receive(sink, buffer, pad):
    valid, mapping = buffer.map(Gst.MapFlags.READ)
    if not valid:
        return
    try:
        sample = (buffer.pts, buffer.duration, len(mapping.data), mapping.data[3], mapping.data[-1])
        samples.append(sample)
        if sample[3] == 64:
            first.set()
        if sample[3] == 192:
            second.set()
    finally:
        buffer.unmap(mapping)


output.pipeline.get_by_name("verify_sink").connect("handoff", receive)
try:
    assert output.source.get_property("max-buffers") == 2
    assert output.source.get_property("leaky-type").value_nick == "downstream"
    output.start(Image.new("RGBA", (1920, 1080), (45, 75, 105, 64)))
    assert first.wait(5), output.poll_error() or "Initial frame did not arrive"
    output.update_prepared(output.prepare_frame(Image.new("RGBA", (1920, 1080), (100, 150, 220, 192))))
    assert second.wait(5), output.poll_error() or "Updated frame did not arrive"
    assert output.poll_error() is None
    assert all(item[2] == 1920 * 1080 * 4 for item in samples), samples
    assert all(item[3] == item[4] and item[3] in (64, 192) for item in samples), samples
    assert all(b[0] > a[0] for a, b in zip(samples, samples[1:])), samples
    print(json.dumps({"gstreamer": Gst.version_string(), "sink": "fakesink", "samples": samples}))
finally:
    output.stop()
