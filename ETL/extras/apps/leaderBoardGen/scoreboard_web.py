"""Browser host for scoreboard_app.py using only the Python standard library."""

from __future__ import annotations

import base64
import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse


MAX_REQUEST_BYTES = 35 * 1024 * 1024
IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}


class ScoreboardWebRuntime:
    def __init__(self, core, upload_dir: Path | None = None):
        self.core = core
        self.app_dir = Path(core.__file__).resolve().parent
        self.web_file = self.app_dir / "scoreboard_web.html"
        self.upload_dir = self._select_upload_dir(upload_dir)
        self.lock = threading.RLock()
        self.live_output = None
        self.live_preset = None
        self.live_output_name = None

    def _select_upload_dir(self, requested: Path | None) -> Path:
        candidates = []
        if requested is not None:
            candidates.append(Path(requested))
        configured = os.environ.get("SCOREBOARD_WEB_UPLOAD_DIR", "").strip()
        if configured:
            candidates.append(Path(configured))
        candidates.append(self.app_dir.parents[2] / "output" / "scoreboard_web" / "uploads")
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidates.append(Path(local_app_data) / "Veto" / "ScoreboardMaker" / "uploads")
        candidates.append(Path(tempfile.gettempdir()) / "VetoScoreboardMaker" / "uploads")

        failures = []
        for candidate in candidates:
            try:
                candidate = candidate.expanduser().resolve()
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / f".write-check-{uuid.uuid4().hex}"
                probe.write_bytes(b"ok")
                probe.unlink()
                return candidate
            except OSError as exc:
                failures.append(f"{candidate}: {exc}")
        raise RuntimeError(
            "No writable scoreboard upload folder was found. " + " | ".join(failures)
        )

    def storage_status(self) -> Dict[str, Any]:
        return {
            "path": str(self.upload_dir),
            "writable": self.upload_dir.is_dir() and os.access(self.upload_dir, os.W_OK),
        }

    def bootstrap(self) -> Dict[str, Any]:
        return {
            "template_names": dict(zip(self.core.TEMPLATE_KEYS, self.core.TEMPLATE_NAMES)),
            "defaults": copy.deepcopy(self.core.DEFAULT_CONFIGS),
            "text_targets": {
                key: [{"key": role, "label": label} for role, label in targets]
                for key, targets in self.core.TEXT_STYLE_TARGETS.items()
            },
            "fonts": list(self.core.FONT_CHOICES),
            "text_cases": list(self.core.TEXT_CASE_CHOICES),
            "video_presets": list(self.core.VIDEO_EXPORT_PRESETS),
            "decklink_outputs": self.core.DECKLINK_OUTPUTS,
            "canvas_sizes": {
                "t1": list(self.core.T1_SIZES),
                "t2": list(self.core.T2_SIZES),
                "t3": list(self.core.T3_SIZES),
                "t4": list(self.core.T4_SIZES),
            },
        }

    def normalized_config(self, template: str, value: Any) -> Dict[str, Any]:
        if template not in self.core.TEMPLATE_KEYS:
            raise ValueError("Unknown scoreboard template.")
        config = self.core.normalise_project_configs({template: value})[template]
        self._validate_image_paths(template, config)
        return config

    def _validate_image_paths(self, template: str, config: Dict[str, Any]) -> None:
        keys = {
            "t1": ("photo_path", "player_path", "logo_path"),
            "t2": ("photo_a", "photo_b"),
            "t3": ("photo_a", "photo_b", "logo_path"),
            "t4": (),
        }[template]
        for key in keys:
            config[key] = self._safe_uploaded_path(config.get(key, ""))
        if template == "t4":
            for player in config.get("players", []):
                player["photo"] = self._safe_uploaded_path(player.get("photo", ""))

    def _safe_uploaded_path(self, value: Any) -> str:
        if not value:
            return ""
        try:
            path = Path(str(value)).resolve()
            path.relative_to(self.upload_dir.resolve())
        except (OSError, ValueError):
            return ""
        return str(path) if path.is_file() else ""

    def render(self, template: str, value: Any, update_live: bool = True):
        config = self.normalized_config(template, value)
        image = self.core.RENDERERS[template](config)
        with self.lock:
            if update_live and self.live_output is not None:
                self.live_output.update(image)
        return image, config

    def upload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        name = Path(str(payload.get("name", "image"))).name
        data_url = str(payload.get("data", ""))
        match = re.fullmatch(r"data:([^;,]+);base64,(.+)", data_url, re.DOTALL)
        if not match or match.group(1).lower() not in IMAGE_MIME_EXTENSIONS:
            raise ValueError("Upload a supported PNG, JPG, GIF, WebP, BMP, or AVIF image.")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except ValueError as exc:
            raise ValueError("The uploaded image is not valid base64 data.") from exc
        if not data or len(data) > 25 * 1024 * 1024:
            raise ValueError("Images must be between 1 byte and 25 MB.")
        try:
            with self.core.Image.open(io.BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise ValueError("The uploaded file is not a readable image.") from exc
        extension = IMAGE_MIME_EXTENSIONS[match.group(1).lower()]
        target = self.upload_dir / f"{uuid.uuid4().hex}{extension}"
        try:
            # The UUID target is not exposed until this write completes, so a
            # second temporary file and Windows rename are unnecessary here.
            target.write_bytes(data)
        except OSError as exc:
            raise RuntimeError(
                f"Scoreboard upload storage is not writable: {self.upload_dir}"
            ) from exc
        return {"path": str(target.resolve()), "name": name}

    def start_live(self, template: str, config: Any, preset: str, output_name: str):
        if preset not in self.core.VIDEO_EXPORT_PRESETS:
            raise ValueError("Unknown video format.")
        if output_name not in self.core.DECKLINK_OUTPUTS:
            raise ValueError("Unknown DeckLink output.")
        image, _ = self.render(template, config, update_live=False)
        output = self.core.DeckLinkLiveOutput(
            preset, self.core.DECKLINK_OUTPUTS[output_name]
        )
        output.start(image)
        with self.lock:
            previous = self.live_output
            self.live_output = output
            self.live_preset = preset
            self.live_output_name = output_name
        if previous is not None:
            previous.stop()
        return self.live_status()

    def stop_live(self):
        with self.lock:
            output, self.live_output = self.live_output, None
            self.live_preset = None
            self.live_output_name = None
        if output is not None:
            output.stop()
        return self.live_status()

    def live_status(self):
        with self.lock:
            error = self.live_output.poll_error() if self.live_output is not None else None
        if error:
            self.stop_live()
            return {"active": False, "error": error}
        return {
            "active": self.live_output is not None,
            "preset": self.live_preset,
            "output": self.live_output_name,
        }

    def export_mp4(self, template: str, value: Any, preset: str, duration: int) -> bytes:
        ffmpeg = self.core.locate_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg is not installed or FFMPEG_PATH is not configured.")
        duration = max(1, min(300, int(duration)))
        image, _ = self.render(template, value)
        with tempfile.TemporaryDirectory(prefix="scoreboard_web_mp4_") as directory:
            source = Path(directory) / "frame.png"
            output = Path(directory) / "scoreboard.mp4"
            image.save(source, "PNG")
            result = subprocess.run(
                self.core.build_mp4_command(ffmpeg, source, output, preset, duration),
                capture_output=True,
                text=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                detail = (result.stderr or result.stdout or "FFmpeg failed").strip()
                raise RuntimeError(detail[-1800:])
            return output.read_bytes()


def make_handler(runtime: ScoreboardWebRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VetoScoreboard/1.0"

        def log_message(self, message, *args):
            sys.stderr.write("scoreboard-web: " + message % args + "\n")

        def _send(self, status: int, data: bytes, content_type: str, filename: str = ""):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # Rapid preview changes cancel older browser requests by design.
                pass

        def _json(self, status: int, value: Any):
            self._send(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid Content-Length.") from exc
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body is empty or too large.")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JSON request must be an object.")
            return value

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                if path in {"/", "/scoreboard"}:
                    self._send(200, runtime.web_file.read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/bootstrap":
                    self._json(200, runtime.bootstrap())
                elif path == "/api/live/status":
                    self._json(200, runtime.live_status())
                elif path == "/healthz":
                    self._json(200, {
                        "ok": True,
                        "service": "scoreboard-web",
                        "upload_storage": runtime.storage_status(),
                    })
                else:
                    self._json(404, {"error": "Not found"})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            try:
                payload = self._body()
                if path == "/api/render":
                    image, _ = runtime.render(payload.get("template", ""), payload.get("config"))
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png")
                elif path == "/api/upload":
                    self._json(200, runtime.upload(payload))
                elif path == "/api/export/png":
                    template = payload.get("template", "")
                    image, _ = runtime.render(template, payload.get("config"))
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png", f"scoreboard_{template}.png")
                elif path == "/api/export/mp4":
                    template = payload.get("template", "")
                    data = runtime.export_mp4(
                        template, payload.get("config"), payload.get("preset", "HD 1080i50"),
                        payload.get("duration", 10),
                    )
                    self._send(200, data, "video/mp4", f"scoreboard_{template}.mp4")
                elif path == "/api/live/start":
                    self._json(200, runtime.start_live(
                        payload.get("template", ""), payload.get("config"),
                        payload.get("preset", ""), payload.get("output", ""),
                    ))
                elif path == "/api/live/stop":
                    self._json(200, runtime.stop_live())
                else:
                    self._json(404, {"error": "Not found"})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

    return Handler


def run_server(core, host: str = "0.0.0.0", port: int = 8080):
    runtime = ScoreboardWebRuntime(core)
    server = ThreadingHTTPServer((host, port), make_handler(runtime))
    print(f"Scoreboard web editor: http://127.0.0.1:{port}/scoreboard")
    if host not in {"127.0.0.1", "localhost"}:
        print(f"LAN binding enabled on {host}:{port}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop_live()
        server.server_close()
