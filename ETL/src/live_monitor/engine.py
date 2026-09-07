from __future__ import annotations

import datetime as dt
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import LiveConfig
from .parser import CHANNEL_MAPPING_VERSION, parse_gzip_file
from .s3_index import list_recent_relative_keys
from .server import SnapshotServer
from .store import LiveStore


IST = ZoneInfo("Asia/Kolkata")
LOGGER = logging.getLogger("veto.live_monitor")


class InstanceLock:
    """Hold an OS file lock so two processes cannot update the same live database."""

    def __init__(self, path: Path):
        self.path = path
        self._stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a+b")
        self._stream.seek(0)
        if self._stream.read(1) == b"":
            self._stream.write(b"0")
            self._stream.flush()
        self._stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._stream.close()
            self._stream = None
            raise RuntimeError("Another live monitor instance is already running") from exc
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        if self._stream is None:
            return
        self._stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(6):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            # Windows scanners and readers can briefly retain a handle to the
            # published snapshot. Keep atomic replacement, but tolerate that race.
            time.sleep(0.05 * (2**attempt))


class LiveEngine:
    """Coordinates resilient sync, newest-first parsing, and atomic snapshots."""

    def __init__(self, config: LiveConfig, sync_enabled: bool = True):
        self.config = config
        self.sync_enabled = sync_enabled
        self.store = LiveStore(config.database_path)
        self.stop_event = threading.Event()
        self._full_scan_due = time.monotonic() + config.full_scan_seconds
        self._sync_failures = 0
        self._recent_sync_ready = threading.Event()
        self._directory_signatures: dict[Path, int] = {}
        self._file_signatures = self.store.file_signatures()
        self._status_lock = threading.Lock()
        self._runtime = {
            "started_at": time.time(),
            "last_scan_at": None,
            "last_sync_at": None,
            "last_sync_ok": None,
            "sync_started_at": None,
            "sync_in_progress": False,
            "last_backfill_at": None,
            "last_backfill_ok": None,
            "backfill_started_at": None,
            "backfill_in_progress": False,
            "last_snapshot_at": None,
        }

    def request_stop(self, *_args: object) -> None:
        self.stop_event.set()

    def _set_runtime(self, **values: object) -> None:
        with self._status_lock:
            self._runtime.update(values)

    @staticmethod
    def _day_folder(moment: dt.datetime) -> str:
        return moment.strftime("%m-%d-%Y")

    def _recent_directories(self) -> list[Path]:
        now = dt.datetime.now(IST)
        directories: list[Path] = []
        for offset in range(self.config.recent_hours + 1):
            moment = now - dt.timedelta(hours=offset)
            day_root = self.config.spool_root / self._day_folder(moment)
            hour = day_root / moment.strftime("%H")
            directories.append(hour if hour.is_dir() else day_root)
        return list(dict.fromkeys(directories))

    def _full_directories(self) -> list[Path]:
        now = dt.datetime.now(IST)
        return [
            self.config.spool_root / self._day_folder(now - dt.timedelta(days=offset))
            for offset in (0, 1)
        ]

    def scan_directories(self, directories: list[Path], force: bool = False) -> int:
        observed = 0
        seen: set[Path] = set()
        for directory in directories:
            if not directory.is_dir():
                continue
            try:
                signature = directory.stat().st_mtime_ns
            except OSError as exc:
                self.store.event("WARNING", "scanner", f"{directory}: {exc}")
                continue
            resolved_directory = directory.resolve()
            if not force and self._directory_signatures.get(resolved_directory) == signature:
                continue
            for root, _dirs, files in os.walk(directory):
                for name in files:
                    if not name.casefold().endswith(".gz"):
                        continue
                    path = Path(root) / name
                    if path in seen:
                        continue
                    seen.add(path)
                    try:
                        path_text = str(path) if path.is_absolute() else str(path.resolve())
                        if not force and path_text in self._file_signatures:
                            continue
                        stat = path.stat()
                        if stat.st_size <= 0:
                            continue
                        signature = (stat.st_size, stat.st_mtime_ns)
                        if self._file_signatures.get(path_text) == signature:
                            continue
                        status = self.store.observe_file(
                            path,
                            stat.st_size,
                            stat.st_mtime_ns,
                            self.config.stable_observations,
                        )
                        if status != "observed":
                            self._file_signatures[path_text] = signature
                        observed += 1
                    except OSError as exc:
                        self.store.event("WARNING", "scanner", f"{path}: {exc}")
            self._directory_signatures[resolved_directory] = signature
        self._set_runtime(last_scan_at=time.time())
        return observed

    def scanner_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                now = time.monotonic()
                directories = self._recent_directories()
                force = False
                if now >= self._full_scan_due:
                    directories = self._full_directories()
                    self._full_scan_due = now + self.config.full_scan_seconds
                    force = True
                self.scan_directories(directories, force=force)
            except Exception as exc:
                LOGGER.exception("Scanner cycle failed")
                self.store.event("ERROR", "scanner", str(exc))
            self.stop_event.wait(self.config.scan_seconds)

    def worker_loop(self) -> None:
        while not self.stop_event.is_set():
            path = self.store.claim_file()
            if path is None:
                self.stop_event.wait(0.25)
                continue
            try:
                batch = parse_gzip_file(path, self.config.watched_paths)
                self.store.finish_file(path, batch)
            except Exception as exc:
                LOGGER.exception("Could not process %s", path)
                self.store.fail_file(path, f"{type(exc).__name__}: {exc}")

    def _rclone(
        self,
        remote: str,
        local: Path,
        timeout: int,
        max_age: str | None = None,
        min_age: str | None = None,
        files_from: Path | None = None,
    ) -> bool:
        local.mkdir(parents=True, exist_ok=True)
        transfer_count = "32" if files_from else "8"
        checker_count = "64" if files_from else "8"
        command = [
            str(self.config.rclone_exe),
            "copy",
            remote,
            str(local),
            "--size-only",
            "--transfers",
            transfer_count,
            "--checkers",
            checker_count,
            "--retries",
            "2",
            "--low-level-retries",
            "3",
            "--contimeout",
            "15s",
            "--timeout",
            "90s",
            "--max-duration",
            f"{max(1, timeout - 30)}s",
            "--stats",
            "0",
        ]
        # Let recent transfers begin while S3 is still paging through this
        # large flat prefix. Sorting by modtime forced a complete listing first.
        if min_age:
            command.append("--fast-list")
        if files_from:
            command.extend(["--files-from-raw", str(files_from), "--no-traverse"])
        if max_age:
            command.extend(["--max-age", max_age])
        if min_age:
            command.extend(["--min-age", min_age])
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as error_stream:
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=error_stream,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                self.store.event("ERROR", "sync", f"{remote}: {exc}")
                return False

            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if self.stop_event.wait(0.25) or time.monotonic() >= deadline:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    reason = "shutdown requested" if self.stop_event.is_set() else "timed out"
                    self.store.event("WARNING", "sync", f"{remote}: {reason}")
                    return False
            if process.returncode:
                error_stream.seek(0)
                message = (error_stream.read() or "rclone failed").strip()[-1500:]
                self.store.event("ERROR", "sync", f"{remote}: {message}")
                return False
        return True

    def sync_once(self) -> bool:
        now = dt.datetime.now(IST)
        moments = [now, now - dt.timedelta(hours=self.config.recent_hours)]
        days = list({moment.date(): moment for moment in moments}.values())
        success = True
        self._set_runtime(sync_started_at=time.time(), sync_in_progress=True)
        try:
            # A run just after midnight also polls the final hours of yesterday.
            for moment in sorted(days, reverse=True):
                remote = f"{self.config.remote_base}/{moment:%m}/{moment:%d}"
                local = self.config.spool_root / self._day_folder(moment)
                key_file = None
                try:
                    keys = list_recent_relative_keys(
                        remote, self.config.recent_hours, local_root=local
                    )
                    if not keys:
                        continue
                    self.config.state_dir.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", newline="\n", delete=False,
                        dir=self.config.state_dir, prefix="recent_keys_", suffix=".txt",
                    ) as stream:
                        stream.write("\n".join(keys))
                        stream.write("\n")
                        key_file = Path(stream.name)
                    synced = self._rclone(remote, local, timeout=900, files_from=key_file)
                except Exception as exc:
                    self.store.event(
                        "WARNING", "sync-index",
                        f"{remote}: parallel S3 index unavailable ({exc}); using rclone listing",
                    )
                    synced = self._rclone(
                        remote, local, timeout=900,
                        max_age=f"{self.config.recent_hours}h",
                    )
                finally:
                    if key_file is not None:
                        key_file.unlink(missing_ok=True)
                success = synced and success
            return success
        except Exception:
            success = False
            raise
        finally:
            self._set_runtime(
                last_sync_at=time.time(), last_sync_ok=success, sync_in_progress=False
            )

    def backfill_once(self) -> bool:
        """Reconcile older files without competing for the recent-file window."""
        now = dt.datetime.now(IST)
        success = True
        self._set_runtime(backfill_started_at=time.time(), backfill_in_progress=True)
        try:
            # Reconcile only the finalized previous day. A second full listing
            # of today competes with and delays the live poll.
            moment = now - dt.timedelta(days=1)
            remote = f"{self.config.remote_base}/{moment:%m}/{moment:%d}"
            local = self.config.spool_root / self._day_folder(moment)
            success = self._rclone(remote, local, timeout=1800) and success
            return success
        except Exception:
            success = False
            raise
        finally:
            self._set_runtime(
                last_backfill_at=time.time(), last_backfill_ok=success,
                backfill_in_progress=False,
            )

    def sync_loop(self) -> None:
        if not self.config.rclone_exe.is_file():
            self.store.event(
                "ERROR", "sync", f"rclone executable not found: {self.config.rclone_exe}"
            )
            return
        while not self.stop_event.is_set():
            try:
                success = self.sync_once()
            except Exception as exc:
                success = False
                LOGGER.exception("Sync cycle failed")
                self.store.event("ERROR", "sync", str(exc))
            self._sync_failures = 0 if success else self._sync_failures + 1
            if success:
                self._recent_sync_ready.set()
            delay = min(300.0, self.config.sync_seconds * (2 ** min(4, self._sync_failures)))
            self.stop_event.wait(delay)

    def backfill_loop(self) -> None:
        while not self.stop_event.is_set() and not self._recent_sync_ready.wait(1):
            pass
        while not self.stop_event.is_set():
            try:
                success = self.backfill_once()
            except Exception as exc:
                success = False
                LOGGER.exception("Backfill cycle failed")
                self.store.event("ERROR", "backfill", str(exc))
            delay = self.config.full_sync_seconds if success else min(
                300.0, self.config.full_sync_seconds
            )
            self.stop_event.wait(delay)

    def publish_snapshot(self) -> dict:
        payload = self.store.snapshot(self.config.dashboard_minutes)
        now = time.time()
        with self._status_lock:
            runtime = dict(self._runtime)
        latest = payload.get("latest_event_ts")
        lag_seconds = max(0, now - float(latest)) if latest else None
        health_issues = []
        if lag_seconds is None:
            health_issues.append("No event data has been processed")
        elif lag_seconds > self.config.health_max_lag_seconds:
            health_issues.append(f"Event data is {int(lag_seconds)} seconds behind")
        if self.sync_enabled and runtime.get("last_sync_ok") is False:
            health_issues.append("Most recent source sync failed")
        payload.update(
            {
                "generated_at": dt.datetime.now(IST).isoformat(),
                "window_minutes": self.config.dashboard_minutes,
                "lag_seconds": lag_seconds,
                "health": {
                    "ok": not health_issues,
                    "status": "ok" if not health_issues else "degraded",
                    "issues": health_issues,
                },
                "runtime": runtime,
                "metric_note": (
                    "All channels and each mapped channel show exact distinct cliIP "
                    "per minute; known device/session counts are exact only where those "
                    "IDs are present in queryStr"
                ),
            }
        )
        atomic_write_json(self.config.snapshot_path, payload)
        self._set_runtime(last_snapshot_at=now)
        return payload

    def snapshot_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.publish_snapshot()
            except Exception as exc:
                LOGGER.exception("Snapshot publication failed")
                self.store.event("ERROR", "snapshot", str(exc))
            self.stop_event.wait(self.config.snapshot_seconds)

    def run(self) -> None:
        with InstanceLock(self.config.state_dir / "live_monitor.lock"):
            reset_files = self.store.ensure_channel_mapping_version(CHANNEL_MAPPING_VERSION)
            self._file_signatures = self.store.file_signatures()
            if reset_files:
                self.store.event(
                    "WARNING",
                    "channel-mapping",
                    f"Rebuilding {reset_files} files for mapping version "
                    f"{CHANNEL_MAPPING_VERSION}",
                )
            recovered = self.store.recover(self.config.stale_processing_seconds)
            if recovered:
                self.store.event(
                    "WARNING", "startup", f"Recovered {recovered} interrupted files"
                )
            for signal_name in ("SIGINT", "SIGTERM"):
                if hasattr(signal, signal_name):
                    signal.signal(getattr(signal, signal_name), self.request_stop)
            # Publish the durable database state and open the status endpoint
            # before the potentially large local-spool reconciliation. The
            # scanner thread performs that reconciliation immediately below.
            self.publish_snapshot()
            server = SnapshotServer(
                self.config.http_host,
                self.config.http_port,
                self.config.snapshot_path,
            )
            server.start()
            LOGGER.info(
                "Live dashboard: http://%s:%s", self.config.http_host, self.config.http_port
            )
            threads = [
                threading.Thread(target=self.scanner_loop, name="scanner"),
                threading.Thread(target=self.snapshot_loop, name="snapshot"),
            ]
            if self.sync_enabled:
                threads.extend([
                    threading.Thread(target=self.sync_loop, name="sync"),
                    threading.Thread(target=self.backfill_loop, name="backfill"),
                ])
            with ThreadPoolExecutor(
                max_workers=self.config.parse_workers,
                thread_name_prefix="parser",
            ) as pool:
                workers = [pool.submit(self.worker_loop) for _ in range(self.config.parse_workers)]
                for thread in threads:
                    thread.start()
                try:
                    while not self.stop_event.wait(1):
                        pass
                finally:
                    self.stop_event.set()
                    server.stop()
                    for thread in threads:
                        thread.join(timeout=10)
                    # Let a claimed gzip finish its atomic database transaction.
                    # Killing it here would only create more recovery work next start.
                    for worker in workers:
                        worker.result()
                    self.publish_snapshot()
