"""Completed recording lookup, browser previews, and bounded file streaming."""

import hashlib
import re
import shutil
import subprocess
import threading
from pathlib import Path


class RecordingLibrary:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.Lock()
        self.jobs = {}
        self.process = None
        self.worker = None
        self.closed = False

    def files(self):
        root = self.manager.recordings_dir.resolve()
        with self.manager.store.connect() as db:
            rows = db.execute(
                "SELECT * FROM recordings WHERE status NOT IN "
                "('starting','recording','stopping') ORDER BY started_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            pattern = Path(row['output_pattern'])
            if '%03d' not in pattern.name:
                continue
            prefix, suffix = pattern.name.split('%03d', 1)
            try:
                folder = pattern.parent.resolve()
                if not folder.is_relative_to(root):
                    continue
                for path in folder.glob('*.mkv'):
                    if not re.fullmatch(re.escape(prefix) + r'\d{3,}' + re.escape(suffix), path.name):
                        continue
                    resolved = path.resolve()
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        continue
                    stat = resolved.stat()
                    if not stat.st_size:
                        continue
                    token = hashlib.sha256((row['id'] + '/' + path.name).encode()).hexdigest()
                    result.append({
                        'id': token, 'channel': row['channel_name'],
                        'date': row['started_at'][:10], 'started_at': row['started_at'],
                        'name': path.name, 'bytes': stat.st_size, 'status': row['status'],
                        '_path': resolved, '_mtime': stat.st_mtime_ns,
                    })
            except OSError:
                continue
        return result

    def get(self, token):
        if not re.fullmatch(r'[a-f0-9]{64}', token):
            raise FileNotFoundError('Recording not found')
        for item in self.files():
            if item['id'] == token:
                return item
        raise FileNotFoundError('Recording not found or still active')

    def target(self, item):
        root = self.manager.recordings_dir.resolve()
        cache = root / '.browser-previews'
        cache.mkdir(exist_ok=True)
        if not cache.resolve().is_relative_to(root):
            raise ValueError('Invalid preview directory')
        return cache / f"{item['id']}_{item['bytes']}_{item['_mtime']}.mp4"

    def preview(self, token, start=False):
        item = self.get(token)
        target = self.target(item)
        if target.is_file() and not target.is_symlink():
            return {'state': 'ready'}
        with self.lock:
            if self.closed:
                raise ValueError('Recorder is shutting down')
            state = self.jobs.get(token, {'state': 'idle'})
            if not start or state['state'] == 'preparing':
                return state
            if self.worker and self.worker.is_alive():
                raise ValueError('Another preview is preparing. Try again when it finishes.')
            if not self.manager.ffmpeg:
                raise ValueError('FFmpeg is unavailable; download the original recording instead.')
            if shutil.disk_usage(target.parent).free < max(2 * 1024**3, item['bytes'] * 2):
                raise ValueError('Not enough free space for a browser preview')
            self.jobs[token] = {'state': 'preparing'}
            self.worker = threading.Thread(target=self._convert, args=(item, target), daemon=True)
            self.worker.start()
            return self.jobs[token]

    def _convert(self, item, target):
        temp = target.with_suffix('.tmp.mp4')
        log = target.with_suffix('.log')
        try:
            with log.open('wb') as stderr:
                with self.lock:
                    if self.closed:
                        return
                    self.process = subprocess.Popen([
                        self.manager.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-y', '-i', str(item['_path']), '-map', '0:v:0', '-map', '0:a:0?',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-threads', '2',
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(temp),
                    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    process = self.process
                code = process.wait(timeout=7200)
                if code:
                    raise ValueError('Preview conversion failed; the original is still downloadable.')
            with self.lock:
                if self.closed:
                    return
                temp.replace(target)
                self.jobs[item['id']] = {'state': 'ready'}
        except Exception:
            with self.lock:
                if self.process and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
                self.jobs[item['id']] = {
                    'state': 'failed', 'error': 'Preview conversion failed. Download the original or retry.'
                }
        finally:
            temp.unlink(missing_ok=True)
            with self.lock:
                self.process = None

    def close(self):
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.terminate()
        if self.worker:
            self.worker.join(timeout=15)


def send_file(handler, path, download=False):
    """Serve one validated file with single-byte-range support for video seeking."""
    with path.open('rb') as source:
        size = path.stat().st_size
        start, end = 0, size - 1
        requested = handler.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            try:
                if not match or not any(match.groups()):
                    raise ValueError()
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), end) if right else end
                else:
                    count = int(right)
                    if count <= 0:
                        raise ValueError()
                    start = max(0, size - count)
                if start > end or start >= size:
                    raise ValueError()
            except ValueError:
                handler.send_response(416)
                handler.send_header('Content-Range', f'bytes */{size}')
                handler.send_header('Content-Length', '0')
                handler.end_headers()
                return
        handler.send_response(206 if requested else 200)
        handler.send_header('Content-Type', 'video/mp4' if path.suffix == '.mp4' else 'video/x-matroska')
        handler.send_header('Content-Length', str(end - start + 1))
        handler.send_header('Accept-Ranges', 'bytes')
        handler.send_header('Cache-Control', 'private, no-store')
        handler.send_header('X-Content-Type-Options', 'nosniff')
        if download:
            from urllib.parse import quote
            handler.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(path.name))
        if requested:
            handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        handler.end_headers()
        if handler.command == 'HEAD':
            return
        source.seek(start)
        remaining = end - start + 1
        try:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
