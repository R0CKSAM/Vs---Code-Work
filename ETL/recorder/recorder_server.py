#!/usr/bin/env python3
"""Local multi-channel HLS preview and crash-resilient FFmpeg recorder."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from recording_library import RecordingLibrary, send_file


ROOT = Path(__file__).resolve().parent
DEFAULT_CHANNELS = ROOT / "channels.json"
DEFAULT_RECORDINGS = ROOT / "recordings"
DEFAULT_DB = ROOT / "recorder_state.sqlite"
INDEX_FILE = ROOT / "recorder_dashboard.html"
LOG = logging.getLogger("veto-recorder")


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._")
    return re.sub(r"\s+", "_", value)[:80] or "channel"


def locate_ffmpeg(explicit: str = "") -> str | None:
    candidates = [
        explicit,
        os.getenv("FFMPEG_PATH", ""),
        str(ROOT.parent / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"),
        str(ROOT.parent / "tools" / "ffmpeg.exe"),
        shutil.which("ffmpeg") or "",
    ]
    located = next(
        (str(Path(item).resolve()) for item in candidates if item and Path(item).is_file()),
        None,
    )
    if located:
        return located
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"), reverse=True)
        if matches:
            return str(matches[0].resolve())
    return None


class RecorderStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS recordings (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT,
                    output_pattern TEXT NOT NULL,
                    pid INTEGER,
                    error TEXT DEFAULT ''
                )
            """)
            db.execute(
                "UPDATE recordings SET status='interrupted', stopped_at=? "
                "WHERE status IN ('starting','recording','stopping')",
                (now_text(),),
            )

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def insert(self, row: dict[str, Any]) -> None:
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO recordings "
                "(id,channel_id,channel_name,status,started_at,output_pattern,pid,error) "
                "VALUES (:id,:channel_id,:channel_name,:status,:started_at,:output_pattern,:pid,:error)",
                row,
            )

    def update(self, recording_id: str, **values: Any) -> None:
        if not values:
            return
        assignments = ",".join(f"{key}=?" for key in values)
        with self.lock, self.connect() as db:
            db.execute(
                f"UPDATE recordings SET {assignments} WHERE id=?",
                (*values.values(), recording_id),
            )

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock, self.connect() as db:
            rows = db.execute(
                "SELECT * FROM recordings ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


class RecorderManager:
    def __init__(self, channels_path: Path, recordings_dir: Path, db_path: Path, ffmpeg: str = ""):
        self.channels_path = channels_path
        self.recordings_dir = recordings_dir
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.store = RecorderStore(db_path)
        self.ffmpeg = locate_ffmpeg(ffmpeg)
        self.lock = threading.RLock()
        self.stopping = False
        self.processes: dict[str, subprocess.Popen] = {}
        self.channel_jobs: dict[str, str] = {}
        self.channels = self._load_channels()
        self.library = RecordingLibrary(self)

    def _load_channels(self) -> dict[str, dict[str, Any]]:
        data = json.loads(self.channels_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("channels.json must contain a list")
        result: dict[str, dict[str, Any]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            channel_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()
            url = str(item.get("hls_url", "")).strip()
            if not channel_id or not name or channel_id in result:
                raise ValueError(f"Invalid or duplicate channel: {channel_id!r}")
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"Invalid HLS URL for {name}")
            result[channel_id] = {
                "id": channel_id,
                "name": name,
                "group": str(item.get("group", "Other")).strip() or "Other",
                "hls_url": url,
                "enabled": bool(item.get("enabled", True)) and bool(url),
            }
        return result

    def public_channels(self) -> list[dict[str, Any]]:
        with self.lock:
            active = set(self.channel_jobs)
        return [
            {**channel, "recording": channel["id"] in active}
            for channel in sorted(self.channels.values(), key=lambda row: (row["group"], row["name"]))
        ]

    def system_status(self) -> dict[str, Any]:
        usage = shutil.disk_usage(self.recordings_dir)
        with self.lock:
            active = len(self.processes)
        return {
            "service": "veto-recorder",
            "pid": os.getpid(),
            "stopping": self.stopping,
            "ffmpeg_ready": bool(self.ffmpeg),
            "ffmpeg_path": self.ffmpeg or "",
            "active_recordings": active,
            "free_disk_bytes": usage.free,
            "recordings_dir": str(self.recordings_dir),
            "server_time": now_text(),
        }

    def start(self, channel_ids: list[str], segment_minutes: int = 30) -> dict[str, Any]:
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg is not installed or configured")
        if shutil.disk_usage(self.recordings_dir).free < 2 * 1024**3:
            raise RuntimeError("Less than 2 GB free disk space remains")
        segment_seconds = max(5, min(360, int(segment_minutes))) * 60
        started, skipped, errors = [], [], []
        for channel_id in dict.fromkeys(channel_ids):
            channel = self.channels.get(channel_id)
            if not channel or not channel["enabled"]:
                skipped.append({"channel_id": channel_id, "reason": "Feed URL unavailable"})
                continue
            with self.lock:
                if channel_id in self.channel_jobs:
                    skipped.append({"channel_id": channel_id, "reason": "Already recording"})
                    continue
            try:
                with self.lock:
                    if self.stopping:
                        raise RuntimeError("Recorder is shutting down")
                    if channel_id in self.channel_jobs:
                        continue
                    started.append(self._start_one(channel, segment_seconds))
            except Exception as exc:
                LOG.exception("Could not start %s", channel["name"])
                errors.append({"channel_id": channel_id, "reason": str(exc)})
        return {"started": started, "skipped": skipped, "errors": errors}

    def _start_one(self, channel: dict[str, Any], segment_seconds: int) -> dict[str, Any]:
        started = datetime.now().astimezone()
        folder = self.recordings_dir / started.strftime("%Y-%m-%d") / safe_name(channel["name"])
        folder.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y-%m-%d_%H-%M-%S")
        pattern = folder / f"{safe_name(channel['name'])}_{stamp}_part_%03d.mkv"
        recording_id = uuid.uuid4().hex
        command = [
            self.ffmpeg,
            "-hide_banner", "-loglevel", "warning", "-nostats",
            "-reconnect", "1", "-reconnect_streamed", "1",
            "-reconnect_delay_max", "10", "-rw_timeout", "15000000",
            "-i", channel["hls_url"],
            "-map", "0:v:0?", "-map", "0:a?", "-c", "copy",
            "-f", "segment", "-segment_time", str(segment_seconds),
            "-reset_timestamps", "1", "-strftime", "0", str(pattern),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        row = {
            "id": recording_id,
            "channel_id": channel["id"],
            "channel_name": channel["name"],
            "status": "recording",
            "started_at": started.isoformat(timespec="seconds"),
            "output_pattern": str(pattern),
            "pid": process.pid,
            "error": "",
        }
        self.store.insert(row)
        with self.lock:
            self.processes[recording_id] = process
            self.channel_jobs[channel["id"]] = recording_id
        threading.Thread(
            target=self._watch, args=(recording_id, channel["id"], process), daemon=True
        ).start()
        LOG.info("Recording %s as %s (pid %s)", channel["name"], recording_id, process.pid)
        return row

    def _watch(self, recording_id: str, channel_id: str, process: subprocess.Popen) -> None:
        error_text = process.stderr.read()[-4000:] if process.stderr else ""
        code = process.wait()
        with self.lock:
            requested_stop = recording_id not in self.processes
            self.processes.pop(recording_id, None)
            if self.channel_jobs.get(channel_id) == recording_id:
                self.channel_jobs.pop(channel_id, None)
        status = "stopped" if requested_stop and code == 0 else "failed" if code else "stopped"
        self.store.update(
            recording_id,
            status=status,
            stopped_at=now_text(),
            error=error_text.strip() if code else "",
        )

    def stop(self, recording_ids: list[str] | None = None, channel_ids: list[str] | None = None) -> dict[str, Any]:
        with self.lock:
            ids = list(recording_ids or [])
            ids.extend(self.channel_jobs[item] for item in channel_ids or [] if item in self.channel_jobs)
            if not ids:
                ids = list(self.processes)
        stopped = []
        for recording_id in dict.fromkeys(ids):
            with self.lock:
                process = self.processes.pop(recording_id, None)
            if not process:
                continue
            self.store.update(recording_id, status="stopping")
            try:
                if process.stdin:
                    process.stdin.write("q\n")
                    process.stdin.flush()
                process.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            stopped.append(recording_id)
        return {"stopped": stopped}

    def shutdown(self) -> None:
        with self.lock:
            self.stopping = True
        self.stop()
        self.library.close()


class RecorderHandler(SimpleHTTPRequestHandler):
    manager: RecorderManager

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == '/api/library':
            self._json({'files': [
                {key: value for key, value in item.items() if not key.startswith('_')}
                for item in self.manager.library.files()
            ]})
            return
        match = re.fullmatch(r'/api/library/([a-f0-9]{64})/(download|preview|video)', path)
        if match:
            token, action = match.groups()
            try:
                item = self.manager.library.get(token)
                if action == 'download':
                    send_file(self, item['_path'], download=True)
                elif action == 'preview':
                    self._json(self.manager.library.preview(token))
                else:
                    target = self.manager.library.target(item)
                    if self.manager.library.preview(token)['state'] != 'ready':
                        self._json({'error': 'Preview not ready'}, 409)
                    else:
                        send_file(self, target)
            except (FileNotFoundError, ValueError, OSError):
                self._json({'error': 'Recording unavailable'}, 404)
            return
        if path == "/api/channels":
            self._json({"channels": self.manager.public_channels()})
        elif path == "/api/status":
            self._json(self.manager.system_status())
        elif path == "/api/recordings":
            self._json({"recordings": self.manager.store.recent()})
        elif path in {"/", "/recorder"}:
            self.path = "/recorder_dashboard.html"
            super().do_GET()
        elif path.startswith("/api/"):
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        else:
            self._json({'error': 'Not found'}, HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:
        match = re.fullmatch(r'/api/library/([a-f0-9]{64})/(download|video)', urlparse(self.path).path)
        if not match:
            self.send_error(404)
            return
        try:
            item = self.manager.library.get(match[1])
            target = item['_path'] if match[2] == 'download' else self.manager.library.target(item)
            if target.is_symlink() or not target.is_file():
                raise FileNotFoundError()
            send_file(self, target, download=match[2] == 'download')
        except (OSError, ValueError):
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._body()
        try:
            preview = re.fullmatch(r'/api/library/([a-f0-9]{64})/preview', path)
            if preview:
                self._json(self.manager.library.preview(preview[1], start=True))
            elif path == "/api/recordings/start":
                ids = body.get("channel_ids", [])
                if not isinstance(ids, list) or not ids:
                    raise ValueError("Select at least one channel")
                self._json(self.manager.start([str(item) for item in ids], body.get("segment_minutes", 30)))
            elif path == "/api/recordings/stop":
                recording_ids = body.get("recording_ids")
                channel_ids = body.get("channel_ids")
                self._json(self.manager.stop(
                    [str(item) for item in recording_ids] if isinstance(recording_ids, list) else None,
                    [str(item) for item in channel_ids] if isinstance(channel_ids, list) else None,
                ))
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except FileNotFoundError:
            self._json({'error': 'Recording not found'}, HTTPStatus.NOT_FOUND)
        except (RuntimeError, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--channels", type=Path, default=DEFAULT_CHANNELS)
    parser.add_argument("--recordings", type=Path, default=DEFAULT_RECORDINGS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ffmpeg", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Bind before opening the state store: duplicate launches must not mark
    # the running instance's recordings as interrupted.
    server = ThreadingHTTPServer((args.host, args.port), RecorderHandler)
    try:
        manager = RecorderManager(args.channels, args.recordings, args.database, args.ffmpeg)
    except Exception:
        server.server_close()
        raise
    RecorderHandler.manager = manager
    stop_file = ROOT / "logs" / f"recorder_{args.port}.stop"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.unlink(missing_ok=True)
    server.timeout = 0.5
    LOG.info("Recorder dashboard: http://%s:%s/recorder", args.host, args.port)
    LOG.info("FFmpeg: %s", manager.ffmpeg or "not found; preview-only mode")
    try:
        while not stop_file.exists():
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        server.server_close()
        stop_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
