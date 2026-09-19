"""Isolated HTTP smoke server. No GStreamer or SDI hardware is used."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime, make_handler
from test_alpha_output import MemoryOutput


class BrowserMemoryOutput(MemoryOutput):
    prepare_frame = core.DeckLinkLiveOutput.prepare_frame
    update_prepared = core.DeckLinkLiveOutput.update_prepared


def reject_hardware(*args, **kwargs):
    raise AssertionError("Hardware access is forbidden in this browser test")


core.DeckLinkLiveOutput = BrowserMemoryOutput
core.load_gstreamer = reject_hardware

with tempfile.TemporaryDirectory(prefix="browser-memory-", dir=Path(__file__).parent) as directory:
    runtime = ScoreboardWebRuntime(core, Path(directory) / "uploads")
    server = ThreadingHTTPServer(("127.0.0.1", 8094), make_handler(runtime))
    expiry = threading.Timer(180, server.shutdown)
    expiry.daemon = True
    expiry.start()
    print("Memory-only browser test: http://127.0.0.1:8094/scoreboard", flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        expiry.cancel()
        runtime.stop_live(force=True)
        server.server_close()
