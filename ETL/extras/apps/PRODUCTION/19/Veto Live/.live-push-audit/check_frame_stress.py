"""Stress prepared-frame swaps and bounded backpressure without opening SDI."""
import json
import threading
import time

from PIL import Image

import scoreboard_app as core


Gst = core.load_gstreamer()
description = core.build_decklink_pipeline("HD 1080i50", 0, external_key=True)
description = description.rsplit(" ! ", 1)[0] + " ! fakesink name=verify_sink sync=true signal-handoffs=true"
description = description.replace("queue max-size-buffers", "queue name=verify_queue max-size-buffers")
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
queue = output.pipeline.get_by_name("verify_queue")
samples = []
levels = []
throttle = threading.Event()
initial = threading.Event()
recovered = threading.Event()
allowed_alpha = {16, 250, *range(40, 44), *range(100, 104)}
prepared = {alpha: output.prepare_frame(Image.new("RGBA", (1920, 1080), (45, 95, 145, alpha))) for alpha in allowed_alpha}
started = time.perf_counter()


def receive(sink, buffer, pad):
    valid, mapping = buffer.map(Gst.MapFlags.READ)
    if not valid:
        return
    try:
        data = mapping.data
        alpha = tuple(data[index] for index in (3, 1920 * 4 + 3, len(data) // 2 + 3, len(data) - 1))
        uniform_alpha = bytes(data[3::4]).count(alpha[0]) == 1920 * 1080
        samples.append((time.perf_counter() - started, buffer.pts, buffer.duration, len(data), alpha, uniform_alpha))
        if alpha[0] == 16:
            initial.set()
        if alpha[0] == 250:
            recovered.set()
    finally:
        buffer.unmap(mapping)
    if throttle.is_set():
        time.sleep(0.1)


def publish(alpha):
    output.update_prepared(prepared[alpha])
    levels.append((output.source.get_property("current-level-buffers"), queue.get_property("current-level-buffers")))


output.pipeline.get_by_name("verify_sink").connect("handoff", receive)
try:
    output.start(Image.new("RGBA", (1920, 1080), (45, 95, 145, 16)))
    assert initial.wait(5), output.poll_error() or "Initial frame did not arrive"
    normal_started = time.perf_counter()
    for index in range(40):
        publish(40 + index % 4)
        time.sleep(max(0, normal_started + (index + 1) * 0.05 - time.perf_counter()))
    normal_finished = time.perf_counter()
    throttle.set()
    stalled_started = time.perf_counter()
    for index in range(20):
        publish(100 + index % 4)
        time.sleep(max(0, stalled_started + (index + 1) * 0.05 - time.perf_counter()))
    throttle.clear()
    restore_started = time.perf_counter()
    publish(250)
    assert recovered.wait(3), output.poll_error() or "Latest frame did not recover"
    restore_finished = time.perf_counter()
    time.sleep(0.2)
    assert output.poll_error() is None
    assert all(sample[3] == 1920 * 1080 * 4 for sample in samples), samples
    assert all(sample[5] and len(set(sample[4])) == 1 and sample[4][0] in allowed_alpha for sample in samples), samples
    assert all(second[1] > first[1] for first, second in zip(samples, samples[1:])), samples
    assert all(sample[2] == 40_000_000 for sample in samples), samples
    assert max(level[0] for level in levels) <= 2, levels
    assert max(level[1] for level in levels) <= 2, levels
    normal = [sample for sample in samples if normal_started - started <= sample[0] < normal_finished - started]
    intervals = [(second[0] - first[0]) * 1000 for first, second in zip(normal, normal[1:])]
    print(json.dumps({
        "gstreamer": Gst.version_string(), "sink": "fakesink", "samples": len(samples),
        "normal_swaps": 40, "normal_seconds": round(normal_finished - normal_started, 3),
        "normal_interval_ms": {"min": round(min(intervals), 2), "mean": round(sum(intervals) / len(intervals), 2), "max": round(max(intervals), 2)},
        "downstream_stall_ms_per_frame": 100, "stall_seconds": round(restore_started - stalled_started, 3),
        "maximum_queued_frames": {"appsrc": max(level[0] for level in levels), "queue": max(level[1] for level in levels)},
        "latest_frame_recovery_ms": round((restore_finished - restore_started) * 1000, 2),
        "latest_alpha": samples[-1][4], "raster_bytes": 1920 * 1080 * 4,
        "all_timestamps_increase": True, "no_blank_or_mixed_alpha_samples": True,
    }))
finally:
    output.stop()
