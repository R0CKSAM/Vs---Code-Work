"""Browser host for scoreboard_app.py using only the Python standard library."""

from __future__ import annotations

import base64
import copy
import io
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse


MAX_REQUEST_BYTES = 35 * 1024 * 1024
SESSION_TIMEOUT_SECONDS = 30
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
        self.live_owner_id = None
        self.sessions: Dict[str, Dict[str, Any]] = {}

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

    @staticmethod
    def _clean_client_id(value: Any) -> str:
        client_id = str(value or "").strip()
        return client_id if re.fullmatch(r"[A-Za-z0-9-]{8,80}", client_id) else ""

    @staticmethod
    def _clean_display_name(value: Any, client_id: str) -> str:
        name = re.sub(r"\s+", " ", str(value or "")).strip()[:40]
        return name or f"Operator {client_id[:4].upper()}"

    @staticmethod
    def _is_local_request(remote_address: str) -> bool:
        try:
            return ipaddress.ip_address(remote_address).is_loopback
        except ValueError:
            return False

    def _purge_sessions_locked(self) -> None:
        cutoff = time.monotonic() - SESSION_TIMEOUT_SECONDS
        stale = [
            client_id for client_id, session in self.sessions.items()
            if session["last_seen"] < cutoff and client_id != self.live_owner_id
        ]
        for client_id in stale:
            self.sessions.pop(client_id, None)

    def register_session(
        self, client_id: Any, display_name: Any, remote_address: str,
    ) -> Dict[str, Any]:
        client_id = self._clean_client_id(client_id) or uuid.uuid4().hex
        now = time.monotonic()
        with self.lock:
            existing = self.sessions.get(client_id, {})
            session = {
                "id": client_id,
                "name": self._clean_display_name(display_name, client_id),
                "address": remote_address,
                "priority": int(existing.get("priority", 50)),
                "last_seen": now,
            }
            self.sessions[client_id] = session
            self._purge_sessions_locked()
            return self._public_session(session)

    def touch_session(self, client_id: Any, remote_address: str) -> Dict[str, Any] | None:
        client_id = self._clean_client_id(client_id)
        if not client_id:
            return None
        with self.lock:
            session = self.sessions.get(client_id)
            if session is None:
                session = {
                    "id": client_id,
                    "name": self._clean_display_name("", client_id),
                    "address": remote_address,
                    "priority": 50,
                    "last_seen": time.monotonic(),
                }
                self.sessions[client_id] = session
            else:
                session["address"] = remote_address
                session["last_seen"] = time.monotonic()
            self._purge_sessions_locked()
            return self._public_session(session)

    def _public_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": session["id"],
            "name": session["name"],
            "address": session["address"],
            "priority": session["priority"],
            "live_owner": session["id"] == self.live_owner_id,
            "age_seconds": max(0, int(time.monotonic() - session["last_seen"])),
        }

    def session_status(self, client_id: Any, remote_address: str) -> Dict[str, Any]:
        requester = self.touch_session(client_id, remote_address)
        with self.lock:
            sessions = sorted(
                (self._public_session(session) for session in self.sessions.values()),
                key=lambda item: (-item["priority"], item["name"].casefold()),
            )
        return {
            "requester": requester,
            "can_manage": self._is_local_request(remote_address),
            "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
            "sessions": sessions,
        }

    def set_session_priority(
        self, target_id: Any, priority: Any, remote_address: str,
    ) -> Dict[str, Any]:
        if not self._is_local_request(remote_address):
            raise PermissionError("Priorities can only be changed from this computer.")
        target_id = self._clean_client_id(target_id)
        try:
            priority = max(0, min(100, int(priority)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Priority must be from 0 to 100.") from exc
        with self.lock:
            session = self.sessions.get(target_id)
            if session is None:
                raise ValueError("That user is no longer online.")
            session["priority"] = priority
            return self._public_session(session)

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
            "t2": ("photo_a", "photo_b", "logo_path"),
            "t3": ("photo_a", "photo_b", "logo_path"),
            "t4": ("logo_path",),
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

    def render(
        self, template: str, value: Any, update_live: bool = True, client_id: str = "",
    ):
        config = self.normalized_config(template, value)
        image = self.core.RENDERERS[template](config)
        with self.lock:
            if (
                update_live and self.live_output is not None
                and self._clean_client_id(client_id) == self.live_owner_id
            ):
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

    def start_live(
        self, template: str, config: Any, preset: str, output_name: str,
        client_id: Any, remote_address: str,
    ):
        if preset not in self.core.VIDEO_EXPORT_PRESETS:
            raise ValueError("Unknown video format.")
        if output_name not in self.core.DECKLINK_OUTPUTS:
            raise ValueError("Unknown DeckLink output.")
        requester = self.touch_session(client_id, remote_address)
        if requester is None:
            raise PermissionError("Register an operator name before starting live output.")
        if requester["priority"] <= 0:
            raise PermissionError("This user has view-only live priority.")
        with self.lock:
            owner = self.sessions.get(self.live_owner_id) if self.live_owner_id else None
            if owner and owner["id"] != requester["id"]:
                if requester["priority"] <= owner["priority"]:
                    raise PermissionError(
                        f"Live output is controlled by {owner['name']} "
                        f"(priority {owner['priority']})."
                    )
            image, _ = self.render(
                template, config, update_live=False, client_id=requester["id"],
            )
            if (
                self.live_output is not None
                and self.live_preset == preset
                and self.live_output_name == output_name
            ):
                self.live_output.update(image)
                self.live_owner_id = requester["id"]
                return self.live_status(requester["id"], remote_address)
            previous = self.live_output
            if previous is not None:
                previous.stop()
                self.live_output = None
                self.live_preset = None
                self.live_output_name = None
                self.live_owner_id = None
            output = self.core.DeckLinkLiveOutput(
                preset, self.core.DECKLINK_OUTPUTS[output_name]
            )
            output.start(image)
            self.live_output = output
            self.live_preset = preset
            self.live_output_name = output_name
            self.live_owner_id = requester["id"]
        return self.live_status(requester["id"], remote_address)

    def stop_live(
        self, client_id: Any = "", remote_address: str = "", force: bool = False,
    ):
        client_id = self._clean_client_id(client_id)
        with self.lock:
            if (
                self.live_output is not None and not force
                and client_id != self.live_owner_id
                and not self._is_local_request(remote_address)
            ):
                owner = self.sessions.get(self.live_owner_id, {})
                raise PermissionError(
                    f"Only {owner.get('name', 'the live operator')} can stop live output."
                )
            output, self.live_output = self.live_output, None
            self.live_preset = None
            self.live_output_name = None
            self.live_owner_id = None
        if output is not None:
            output.stop()
        return self.live_status(client_id, remote_address)

    def live_status(self, client_id: Any = "", remote_address: str = ""):
        client_id = self._clean_client_id(client_id)
        with self.lock:
            error = self.live_output.poll_error() if self.live_output is not None else None
        if error:
            self.stop_live(force=True)
            return {"active": False, "error": error}
        with self.lock:
            owner = self.sessions.get(self.live_owner_id)
        return {
            "active": self.live_output is not None,
            "preset": self.live_preset,
            "output": self.live_output_name,
            "owner_id": self.live_owner_id,
            "owner_name": owner["name"] if owner else None,
            "owned_by_requester": bool(client_id and client_id == self.live_owner_id),
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
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            client_id = query.get("client_id", [""])[0]
            remote_address = self.client_address[0]
            try:
                if path in {"/", "/scoreboard"}:
                    self._send(200, runtime.web_file.read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/bootstrap":
                    self._json(200, runtime.bootstrap())
                elif path == "/api/live/status":
                    self._json(200, runtime.live_status(client_id, remote_address))
                elif path == "/api/sessions":
                    self._json(200, runtime.session_status(client_id, remote_address))
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
                client_id = payload.get("client_id", "")
                remote_address = self.client_address[0]
                if path == "/api/session/register":
                    self._json(200, runtime.register_session(
                        client_id, payload.get("display_name", ""), remote_address,
                    ))
                elif path == "/api/session/heartbeat":
                    self._json(200, runtime.touch_session(client_id, remote_address))
                elif path == "/api/session/priority":
                    self._json(200, runtime.set_session_priority(
                        payload.get("target_id", ""), payload.get("priority"), remote_address,
                    ))
                elif path == "/api/render":
                    runtime.touch_session(client_id, remote_address)
                    image, _ = runtime.render(
                        payload.get("template", ""), payload.get("config"),
                        client_id=client_id,
                    )
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png")
                elif path == "/api/upload":
                    runtime.touch_session(client_id, remote_address)
                    self._json(200, runtime.upload(payload))
                elif path == "/api/export/png":
                    runtime.touch_session(client_id, remote_address)
                    template = payload.get("template", "")
                    image, _ = runtime.render(template, payload.get("config"))
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    self._send(200, buffer.getvalue(), "image/png", f"scoreboard_{template}.png")
                elif path == "/api/export/mp4":
                    runtime.touch_session(client_id, remote_address)
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
                        client_id, remote_address,
                    ))
                elif path == "/api/live/stop":
                    self._json(200, runtime.stop_live(client_id, remote_address))
                else:
                    self._json(404, {"error": "Not found"})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except PermissionError as exc:
                self._json(403, {"error": str(exc)})
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
        runtime.stop_live(force=True)
        server.server_close()
