"""Regression checks for operator ownership in the deployed scoreboard copy."""

import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


WEB_PATH = Path(__file__).resolve().parents[1] / "extras/apps/PRODUCTION/Veto OTT/scoreboard_web.py"
SPEC = importlib.util.spec_from_file_location("production_scoreboard_web", WEB_PATH)
web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web)


class FakeOutput:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True

    def poll_error(self):
        return None


def runtime():
    instance = web.ScoreboardWebRuntime.__new__(web.ScoreboardWebRuntime)
    instance.lock = threading.RLock()
    instance.sessions = {}
    instance.live_owner_id = None
    instance.live_output = None
    instance.media_playback = None
    instance.program_revision = "revision-1"
    instance.live_preset = None
    instance.live_output_name = None
    instance.on_air = None
    instance.program_frame = None
    instance.program_name = ""
    instance.program_layout = ""
    instance.live_clear_mode = "black"
    return instance


def test_known_client_id_cannot_be_re_registered_or_touched_without_token():
    app = runtime()
    owner = app.register_session("operator-0001", "Director", "192.168.50.10")
    app.sessions[owner["id"]]["priority"] = 100

    other = app.register_session(owner["id"], "Impostor", "192.168.50.11")
    assert other["id"] != owner["id"]
    assert other["priority"] == 50
    assert app.touch_session(owner["id"], "192.168.50.11", other["token"]) is None
    assert app.sessions[owner["id"]]["address"] == "192.168.50.10"
    assert app.register_session(owner["id"], "Director", "192.168.50.10", owner["token"])["priority"] == 100
    assert all("token" not in user for user in app.session_status(other["id"], "192.168.50.11", other["token"])["sessions"])


def test_live_owner_requires_matching_token_to_stop_output():
    app = runtime()
    owner = app.register_session("operator-0001", "Director", "192.168.50.10")
    output = FakeOutput()
    app.live_owner_id = owner["id"]
    app.live_output = output

    assert not app.live_status(owner["id"], "192.168.50.11")["owned_by_requester"]
    assert app.live_status(owner["id"], "192.168.50.10", owner["token"])["owned_by_requester"]
    with pytest.raises(PermissionError):
        app.stop_live(owner["id"], "192.168.50.11", token="wrong-token")
    assert app.live_output is output and not output.stopped

    app.stop_live(owner["id"], "192.168.50.10", token=owner["token"])
    assert output.stopped and app.live_output is None


def test_live_stop_http_route_requires_token_even_on_host():
    app = runtime()
    app.core = SimpleNamespace(WEB_TEMPLATE_KEYS=())
    with ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(app)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(path, payload, token=""):
            request = Request(
                base + path,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Operator-Token": token},
            )
            with urlopen(request, timeout=3) as response:
                return json.load(response)

        try:
            owner = post("/api/session/register", {"client_id": "operator-0001", "display_name": "Director"})
            output = FakeOutput()
            app.live_owner_id = owner["id"]
            app.live_output = output
            with pytest.raises(HTTPError) as denied:
                post("/api/live/stop", {"client_id": owner["id"]})
            assert denied.value.code == 403
            assert not output.stopped

            result = post("/api/live/stop", {"client_id": owner["id"]}, owner["token"])
            assert result["active"] is False
            assert output.stopped
        finally:
            server.shutdown()
            thread.join(timeout=3)
