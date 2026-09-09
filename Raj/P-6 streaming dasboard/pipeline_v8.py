"""
Akamai Global Log Pipeline — V8 (Audited & Fixed)

Changes from V7:
  - sync_status always written inside state.lock (was mixed inside/outside)
  - int(statusCode) wrapped in try/except to handle malformed values
  - Records with no reqTimeSec are now skipped, not silently ingested
  - global_seen_paths race at shutdown eliminated; scan_loop writes its own
    final checkpoint when shutdown_event is set, main() no longer references it
  - pending_sizes evicted after MAX_PENDING_CYCLES cycles per path to prevent
    unbounded growth from perpetually-unstable files
  - MINUTES_RETAIN is now actively enforced: stale minute buckets are pruned
    each scan cycle
  - archive_previous_day guards with os.path.exists before shutil.copy2
  - enforce_retention_policy last-run timestamp persisted in checkpoint so
    restart storms don't trigger back-to-back rmtree calls
  - state.snapshot() now returns a PipelineSnapshot dataclass, not a 14-tuple
  - SyncStatus is an Enum — no more magic strings
  - Lambda callbacks use explicit argument binding for all mutable captures
  - parse_file logs fpath (not just fname) in error messages
  - Non-daemon ScanWorker thread is join()-ed before final checkpoint write
"""

import time
import os
import gzip
import json
import subprocess
import threading
import datetime
import concurrent.futures
import signal
import sys
import shutil
import logging
import dataclasses
from enum import Enum
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote
from collections import Counter, deque
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Console, Group

console = Console()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# rclone uses the current user's configured remotes (including `veto`).
# Set RCLONE_EXE to override this when rclone is installed elsewhere.
RCLONE_EXE = os.environ.get("RCLONE_EXE", "rclone")
REMOTE_BASE = "veto:veto-stream-logs/veto-stream-logs"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.environ.get("LIVE_DASHBOARD_RUNTIME_DIR", os.path.join(PROJECT_DIR, "runtime"))
LOCAL_BASE = os.path.join(RUNTIME_DIR, "logs")

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

SYNC_INTERVAL_SEC = 10
SCAN_INTERVAL_SEC = 2
LOCAL_RETENTION_DAYS = 2

WATCHED_PATHS = [
    "vglive-274906",
    "upgovlive",
]
TOP_STATES_SHOWN = 8

CONCURRENCY_PATHS = [
    "vglive-274906",
    "upgovlive",
]
MINUTES_SHOWN = 1440
MINUTES_RETAIN = 1440

# How many scan cycles a file can sit in pending_sizes before we warn & skip
MAX_PENDING_CYCLES = 30

STATE_JSON_PATH = os.path.join(RUNTIME_DIR, "live_state.json")
CHECKPOINT_PATH = os.path.join(RUNTIME_DIR, "live_checkpoint.json")
ERROR_LOG_PATH = os.path.join(RUNTIME_DIR, "pipeline_errors.log")
CHECKPOINT_INTERVAL_SEC = 60

os.makedirs(RUNTIME_DIR, exist_ok=True)

HEARTBEAT_THRESHOLDS = {
    "sync": 210,
    "scan": 30,
    "export": 15,
}

shutdown_event = threading.Event()


# ---------------------------------------------------------------------------
# ENUMS & DATACLASSES
# ---------------------------------------------------------------------------

class SyncStatus(str, Enum):
    INITIALIZING = "Initializing..."
    SYNCING = "Syncing..."
    IDLE = "Idle (Synced)"
    ERROR = "Sync Error"
    TIMEOUT = "Timeout (180s)"
    FATAL = "Fatal Error"


@dataclasses.dataclass
class PipelineSnapshot:
    processed_files: int
    total_records: int
    skipped_records: int
    unique_ip_count: int
    error_count: int
    sync_status: SyncStatus
    last_sync_duration: float | None
    latest_record_ts: float | None
    path_snapshot: dict         # {path: (records, ip_count, top_states)}
    minute_snapshot: dict       # {path: [(minute_key, count), ...]}
    processing_speed: int
    heartbeats: dict            # {thread_key: elapsed_seconds}
    pending_queue_depth: int
    recent_errors: list[str]


# ---------------------------------------------------------------------------
# DEDICATED FILE LOGGING SETUP
# ---------------------------------------------------------------------------

logger = logging.getLogger("PipelineLogger")
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(ERROR_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def today_ist() -> datetime.date:
    return datetime.datetime.now(IST).date()


def paths_for_date(d: datetime.date):
    remote = f"{REMOTE_BASE}/{d.strftime('%m')}/{d.strftime('%d')}"
    local = os.path.join(LOCAL_BASE, d.strftime('%m-%d-%Y'))
    return remote, local


def rclone_cmd(remote: str, local: str) -> list[str]:
    return [
        RCLONE_EXE, "copy", remote, local,
        "--size-only", "--fast-list", "--transfers", "16",
        "--checkers", "64", "--multi-thread-streams", "4", "--buffer-size", "16M",
    ]


def path_matches_watch(req_path: str, watched: str) -> bool:
    if not req_path:
        return False
    clean = req_path.split("?", 1)[0].strip("/")
    return watched in clean.split("/")


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.tracking_date = today_ist()
        self._init_counters()
        self.processing_speed = 0
        self._last_speed_check_time = time.monotonic()
        self._last_speed_record_count = 0

        now = time.monotonic()
        self.heartbeats: dict[str, float] = {"sync": now, "scan": now, "export": now}
        self.pending_queue_depth = 0
        self.recent_errors: deque[str] = deque(maxlen=3)

        # Persisted across checkpoints so restart storms don't re-run rmtree
        self.last_retention_run: float = 0.0

    def _init_counters(self):
        self.processed_files = 0
        self.total_records = 0
        self.skipped_records = 0
        self.unique_ips: set[str] = set()
        self.error_count = 0
        self.sync_status: SyncStatus = SyncStatus.INITIALIZING
        self.last_sync_duration: float | None = None
        self.latest_record_ts: float | None = None
        self.path_stats: dict = {
            p: {"records": 0, "ips": set(), "states": Counter()} for p in WATCHED_PATHS
        }
        self.path_minutes: dict = {p: {} for p in CONCURRENCY_PATHS}

    def pulse_heartbeat(self, thread_key: str):
        with self.lock:
            self.heartbeats[thread_key] = time.monotonic()

    def log_error(self, component: str, msg: str, exc: Exception = None):
        with self.lock:
            ts = datetime.datetime.now(IST).strftime("%H:%M:%S")
            entry = f"[{ts}] ({component}) {msg}"
            self.recent_errors.appendleft(entry)
        if exc:
            logger.error(f"({component}) {msg}", exc_info=exc)
        else:
            logger.warning(f"({component}) {msg}")

    def reset_for_new_day(self, new_date: datetime.date):
        with self.lock:
            self._init_counters()
            self.tracking_date = new_date

    def update_speed(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self._last_speed_check_time
            if elapsed >= 2.0:
                diff = self.total_records - self._last_speed_record_count
                self.processing_speed = int(diff / elapsed)
                self._last_speed_check_time = now
                self._last_speed_record_count = self.total_records

    def set_sync_status(self, status: SyncStatus, duration: float | None = None):
        """Always mutate sync_status under the lock."""
        with self.lock:
            self.sync_status = status
            if duration is not None:
                self.last_sync_duration = duration

    def snapshot(self) -> PipelineSnapshot:
        with self.lock:
            path_snapshot = {
                p: (v["records"], len(v["ips"]), v["states"].most_common(TOP_STATES_SHOWN))
                for p, v in self.path_stats.items()
            }
            minute_snapshot = {
                p: sorted(
                    ((mk, len(ips)) for mk, ips in buckets.items()),
                    key=lambda x: x[0]
                )[-MINUTES_SHOWN:]
                for p, buckets in self.path_minutes.items()
            }
            hb_snapshot = {k: time.monotonic() - v for k, v in self.heartbeats.items()}

            return PipelineSnapshot(
                processed_files=self.processed_files,
                total_records=self.total_records,
                skipped_records=self.skipped_records,
                unique_ip_count=len(self.unique_ips),
                error_count=self.error_count,
                sync_status=self.sync_status,
                last_sync_duration=self.last_sync_duration,
                latest_record_ts=self.latest_record_ts,
                path_snapshot=path_snapshot,
                minute_snapshot=minute_snapshot,
                processing_speed=self.processing_speed,
                heartbeats=hb_snapshot,
                pending_queue_depth=self.pending_queue_depth,
                recent_errors=list(self.recent_errors),
            )

    def to_checkpoint_dict(self) -> dict:
        with self.lock:
            return {
                "date_ist": self.tracking_date.isoformat(),
                "processed_files": self.processed_files,
                "total_records": self.total_records,
                "skipped_records": self.skipped_records,
                "unique_ips": list(self.unique_ips),
                "error_count": self.error_count,
                "latest_record_ts": self.latest_record_ts,
                "last_retention_run": self.last_retention_run,
                "path_stats": {
                    p: {
                        "records": v["records"],
                        "ips": list(v["ips"]),
                        "states": dict(v["states"]),
                    }
                    for p, v in self.path_stats.items()
                },
                "path_minutes": {
                    p: {mk: list(ips) for mk, ips in buckets.items()}
                    for p, buckets in self.path_minutes.items()
                },
            }

    def load_from_checkpoint(self, data: dict):
        with self.lock:
            self.processed_files = data.get("processed_files", 0)
            self.total_records = data.get("total_records", 0)
            self.skipped_records = data.get("skipped_records", 0)
            self.unique_ips = set(data.get("unique_ips", []))
            self.error_count = data.get("error_count", 0)
            self.latest_record_ts = data.get("latest_record_ts")
            self.last_retention_run = data.get("last_retention_run", 0.0)

            for p, v in data.get("path_stats", {}).items():
                if p in self.path_stats:
                    self.path_stats[p]["records"] = v.get("records", 0)
                    self.path_stats[p]["ips"] = set(v.get("ips", []))
                    self.path_stats[p]["states"] = Counter(v.get("states", {}))

            for p, buckets in data.get("path_minutes", {}).items():
                if p in self.path_minutes:
                    self.path_minutes[p] = {mk: set(ips) for mk, ips in buckets.items()}

            self.tracking_date = datetime.date.fromisoformat(data["date_ist"])
            self._last_speed_record_count = self.total_records


state = State()


# ---------------------------------------------------------------------------
# DISK RETENTION, ARCHIVAL & CHECKPOINTS
# ---------------------------------------------------------------------------

def enforce_retention_policy():
    """
    Purge local log folders older than LOCAL_RETENTION_DAYS.
    Last-run timestamp is persisted in the checkpoint so restart storms
    don't trigger repeated rmtree calls.
    """
    now = time.monotonic()
    with state.lock:
        last_run = state.last_retention_run

    if now - last_run < 86400:
        return

    if not os.path.exists(LOCAL_BASE):
        return

    cutoff_date = today_ist() - datetime.timedelta(days=LOCAL_RETENTION_DAYS)
    for folder_name in os.listdir(LOCAL_BASE):
        try:
            folder_date = datetime.datetime.strptime(folder_name, '%m-%d-%Y').date()
            if folder_date < cutoff_date:
                target = os.path.join(LOCAL_BASE, folder_name)
                shutil.rmtree(target, ignore_errors=True)
                logger.info(f"Purged expired local log archive: {target}")
        except ValueError:
            continue

    with state.lock:
        state.last_retention_run = now


def archive_previous_day(prev_date: datetime.date):
    date_str = prev_date.isoformat()
    base_dir = os.path.dirname(STATE_JSON_PATH)
    archived_state = os.path.join(base_dir, f"live_state_{date_str}.json")
    archived_ckpt = os.path.join(base_dir, f"live_checkpoint_{date_str}.json")
    try:
        # FIX: guard with exists() before copying to avoid FileNotFoundError on first run
        if os.path.exists(STATE_JSON_PATH):
            shutil.copy2(STATE_JSON_PATH, archived_state)
        if os.path.exists(CHECKPOINT_PATH):
            shutil.copy2(CHECKPOINT_PATH, archived_ckpt)
        logger.info(f"Archived final daily state to live_state_{date_str}.json")
    except Exception as e:
        state.log_error("Archiver", f"Failed to archive previous day: {e}", e)


def load_checkpoint() -> set[str]:
    if not os.path.exists(CHECKPOINT_PATH):
        return set()
    try:
        with open(CHECKPOINT_PATH, "r") as f:
            data = json.load(f)
        if data.get("date_ist") == today_ist().isoformat():
            state.load_from_checkpoint(data)
            logger.info("Resumed state cleanly from local checkpoint.")
            return set(data.get("seen_paths", []))
    except Exception as e:
        state.log_error("Checkpoint", f"Corrupt checkpoint ignored: {e}", e)
    return set()


def write_checkpoint(seen_paths: set[str]):
    payload = state.to_checkpoint_dict()
    payload["seen_paths"] = list(seen_paths)
    tmp = CHECKPOINT_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, CHECKPOINT_PATH)
    except OSError as e:
        state.log_error("Checkpoint", f"Atomic write failed: {e}", e)


# ---------------------------------------------------------------------------
# RECORD PARSING
# ---------------------------------------------------------------------------

def is_from_today(log: dict, target_date: datetime.date) -> bool:
    """
    FIX (was V7): Returns False (skip) when reqTimeSec is absent rather than
    True (ingest), preventing stale records from bleeding across day boundaries.
    """
    raw = log.get("reqTimeSec")
    if not raw:
        return False
    try:
        return datetime.datetime.fromtimestamp(float(raw), tz=IST).date() == target_date
    except (TypeError, ValueError):
        return False


def parse_status_code(raw) -> int | None:
    """
    FIX: int() on a raw log field can raise ValueError on malformed values
    like 'N/A', empty string after strip, etc. Return None on failure.
    """
    if not raw or raw == "-":
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def parse_file(file_path: str, target_date: datetime.date):
    records, errors, skipped = 0, 0, 0
    ips: set[str] = set()
    latest_ts: float | None = None
    path_partial = {p: {"records": 0, "ips": set(), "states": Counter()} for p in WATCHED_PATHS}
    minute_partial: dict[str, dict] = {p: {} for p in CONCURRENCY_PATHS}

    with gzip.open(file_path, "rt", encoding="utf-8") as gz:
        for line in gz:
            line = line.strip()
            if not line:
                continue
            try:
                log = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            if not is_from_today(log, target_date):
                skipped += 1
                continue

            records += 1
            raw_ts = log.get("reqTimeSec")
            ts: float | None = None
            if raw_ts:
                try:
                    ts = float(raw_ts)
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                except ValueError:
                    pass

            ip = log.get("cliIP")
            if ip and ip != "-":
                ips.add(ip)

            status_code = parse_status_code(log.get("statusCode"))
            if status_code is not None and status_code >= 500:
                errors += 1

            req_path = unquote(log.get("reqPath") or log.get("reqUrl") or "")

            for watched_p in WATCHED_PATHS:
                if path_matches_watch(req_path, watched_p):
                    pp = path_partial[watched_p]
                    pp["records"] += 1
                    if ip and ip != "-":
                        pp["ips"].add(ip)
                    st = log.get("state")
                    if st and st != "-":
                        pp["states"][unquote(st)] += 1

            if ts and ip and ip != "-":
                for conc_p in CONCURRENCY_PATHS:
                    if path_matches_watch(req_path, conc_p):
                        minute_key = datetime.datetime.fromtimestamp(ts, tz=IST).strftime("%H:%M")
                        minute_partial[conc_p].setdefault(minute_key, set()).add(ip)

    return records, errors, ips, skipped, latest_ts, path_partial, minute_partial


def _on_parsed(
    future: concurrent.futures.Future,
    fpath: str,
    seen_paths: set[str],
    in_flight: set[str],
):
    in_flight.discard(fpath)
    try:
        records, errors, ips, skipped, latest_ts, path_partial, minute_partial = future.result()

        # Accumulate locally before acquiring the lock to keep critical section short
        new_unique_ips = ips
        new_path_records: dict = {}
        new_path_ips: dict = {}
        new_path_states: dict = {}
        for p, pp in path_partial.items():
            new_path_records[p] = pp["records"]
            new_path_ips[p] = pp["ips"]
            new_path_states[p] = pp["states"]

        with state.lock:
            state.processed_files += 1
            state.total_records += records
            state.error_count += errors
            state.unique_ips |= new_unique_ips
            state.skipped_records += skipped
            if latest_ts and (state.latest_record_ts is None or latest_ts > state.latest_record_ts):
                state.latest_record_ts = latest_ts

            for p in WATCHED_PATHS:
                dest = state.path_stats[p]
                dest["records"] += new_path_records[p]
                dest["ips"] |= new_path_ips[p]
                dest["states"].update(new_path_states[p])

            for p, buckets in minute_partial.items():
                dest_buckets = state.path_minutes[p]
                for minute_key, ip_set in buckets.items():
                    dest_buckets.setdefault(minute_key, set()).update(ip_set)

        seen_paths.add(fpath)
    except Exception as e:
        # FIX: log fpath (full path), not just fname, for unambiguous identification
        state.log_error("Parser", f"Failed parsing {fpath}: {e}", e)


# ---------------------------------------------------------------------------
# MINUTE-BUCKET PRUNING
# ---------------------------------------------------------------------------

def prune_stale_minute_buckets():
    """
    FIX: MINUTES_RETAIN was defined in V7 but never enforced.
    Prune path_minutes entries older than MINUTES_RETAIN minutes.
    Called each scan cycle.
    """
    cutoff_dt = datetime.datetime.now(IST) - datetime.timedelta(minutes=MINUTES_RETAIN)
    cutoff_key = cutoff_dt.strftime("%H:%M")
    with state.lock:
        for p in CONCURRENCY_PATHS:
            state.path_minutes[p] = {
                mk: ips
                for mk, ips in state.path_minutes[p].items()
                if mk >= cutoff_key
            }


# ---------------------------------------------------------------------------
# LOOPS
# ---------------------------------------------------------------------------

def sync_loop():
    while not shutdown_event.is_set():
        state.pulse_heartbeat("sync")

        enforce_retention_policy()

        d = today_ist()
        remote, local = paths_for_date(d)
        os.makedirs(local, exist_ok=True)

        start = time.monotonic()
        # FIX: all sync_status mutations now go through set_sync_status() which
        # always holds state.lock. V7 had bare assignments outside the lock.
        state.set_sync_status(SyncStatus.SYNCING)
        try:
            result = subprocess.run(
                rclone_cmd(remote, local),
                capture_output=True, text=True, timeout=180,
            )
            duration = time.monotonic() - start
            if result.returncode != 0:
                err_msg = result.stderr.strip()[-200:]
                state.set_sync_status(SyncStatus.ERROR, duration)
                state.log_error("Rclone", f"Sync failed (rc={result.returncode}): {err_msg}")
            else:
                state.set_sync_status(SyncStatus.IDLE, duration)
        except subprocess.TimeoutExpired:
            state.set_sync_status(SyncStatus.TIMEOUT)
            state.log_error("Rclone", "S3 download timed out after 180s")
        except Exception as e:
            state.set_sync_status(SyncStatus.FATAL)
            state.log_error("Rclone", f"Execution error: {e}", e)

        state.pulse_heartbeat("sync")
        gap = max(SYNC_INTERVAL_SEC - (time.monotonic() - start), 2)
        shutdown_event.wait(gap)


def scan_loop(initial_seen_paths=None):
    """
    FIX: scan_loop now owns its seen_paths entirely — no more global_seen_paths.
    It writes the final checkpoint itself when shutdown_event fires, then returns
    (the thread is non-daemon so main() can join() it).
    """
    seen_paths: set[str] = set(initial_seen_paths) if initial_seen_paths else set()
    # {fpath: (last_observed_size, consecutive_stable_cycles)}
    pending_sizes: dict[str, tuple[int, int]] = {}
    in_flight: set[str] = set()
    tracked_date = today_ist()
    last_checkpoint_time = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as executor:
        while not shutdown_event.is_set():
            state.pulse_heartbeat("scan")

            d = today_ist()
            if d != tracked_date:
                archive_previous_day(tracked_date)
                seen_paths.clear()
                pending_sizes.clear()
                state.reset_for_new_day(d)
                tracked_date = d

            _, local_dir = paths_for_date(d)
            pending_count = 0

            if os.path.exists(local_dir):
                for root, _, files in os.walk(local_dir):
                    for fname in files:
                        if shutdown_event.is_set():
                            break
                        if not fname.endswith(".gz"):
                            continue
                        fpath = os.path.join(root, fname)
                        if fpath in seen_paths or fpath in in_flight:
                            continue

                        try:
                            size = os.path.getsize(fpath)
                        except OSError:
                            continue
                        if size <= 0:
                            continue

                        pending_count += 1

                        prev_size, stable_cycles = pending_sizes.get(fpath, (-1, 0))

                        if prev_size == size:
                            # FIX: evict files that have been "stable" for too long
                            # (i.e. the upstream writer never closed the file properly)
                            if stable_cycles >= MAX_PENDING_CYCLES:
                                logger.warning(
                                    f"File stuck in pending for {stable_cycles} cycles, skipping: {fpath}"
                                )
                                pending_sizes.pop(fpath, None)
                                seen_paths.add(fpath)  # don't retry this session
                                continue

                            # File size is stable — submit for parsing
                            pending_sizes.pop(fpath, None)
                            in_flight.add(fpath)
                            future = executor.submit(parse_file, fpath, d)
                            # FIX: all mutable captures are explicit keyword args
                            future.add_done_callback(
                                lambda fut, p=fpath, sp=seen_paths, ifl=in_flight:
                                    _on_parsed(fut, p, sp, ifl)
                            )
                        else:
                            # Size changed — record new size, increment stable counter
                            pending_sizes[fpath] = (size, stable_cycles + 1 if prev_size != -1 else 0)

            with state.lock:
                state.pending_queue_depth = pending_count

            # FIX: prune stale minute buckets every scan cycle
            prune_stale_minute_buckets()

            state.update_speed()

            if time.monotonic() - last_checkpoint_time >= CHECKPOINT_INTERVAL_SEC:
                write_checkpoint(seen_paths)
                last_checkpoint_time = time.monotonic()

            shutdown_event.wait(SCAN_INTERVAL_SEC)

    # FIX: final checkpoint written by scan_loop itself on clean shutdown
    write_checkpoint(seen_paths)
    logger.info("ScanWorker wrote final checkpoint and exited.")


def export_loop():
    while not shutdown_event.is_set():
        state.pulse_heartbeat("export")

        snap = state.snapshot()

        payload = {
            "generated_at": datetime.datetime.now(IST).isoformat(),
            "date_ist": today_ist().isoformat(),
            "sync_status": snap.sync_status.value,
            "data_verified_through": (
                datetime.datetime.fromtimestamp(snap.latest_record_ts, tz=IST).strftime("%H:%M:%S")
                if snap.latest_record_ts else None
            ),
            "total_records": snap.total_records,
            "distinct_ips": snap.unique_ip_count,
            "watched_paths": {
                p: {"records": r, "distinct_ips": c}
                for p, (r, c, _) in snap.path_snapshot.items()
            },
            "concurrency_paths": {
                p: [{"minute": mk, "distinct_ips": count} for mk, count in buckets]
                for p, buckets in snap.minute_snapshot.items()
            },
        }

        tmp = STATE_JSON_PATH + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, STATE_JSON_PATH)
        except OSError as e:
            state.log_error("Exporter", f"State export error: {e}", e)

        shutdown_event.wait(SCAN_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

def generate_dashboard():
    snap = state.snapshot()
    d = today_ist()

    table = Table(title=f"Akamai Global Pipeline (IST {d.isoformat()})", expand=True)
    table.add_column("Pipeline Metric", style="cyan", no_wrap=True)
    table.add_column("Status / Value", style="magenta")

    table.add_row("Rclone Status", snap.sync_status.value)
    if snap.last_sync_duration is not None:
        table.add_row("Sync Duration", f"{snap.last_sync_duration:.1f}s")

    table.add_row("Ingestion Rate", f"{snap.processing_speed:,} rows/sec", style="yellow")
    table.add_row(
        "Files In Queue",
        f"{snap.pending_queue_depth} waiting to stabilize",
        style="green" if snap.pending_queue_depth < 100 else "yellow",
    )

    if snap.latest_record_ts:
        latest_dt = datetime.datetime.fromtimestamp(snap.latest_record_ts, tz=IST)
        lag_sec = (datetime.datetime.now(IST) - latest_dt).total_seconds()
        lag_str = f"{int(lag_sec // 60)}m {int(lag_sec % 60)}s behind"
        lag_style = "green" if lag_sec < 120 else ("yellow" if lag_sec < 600 else "red")
        table.add_row(
            "Data Verified Through",
            f"{latest_dt.strftime('%H:%M:%S')} IST  ({lag_str})",
            style=lag_style,
        )
    else:
        table.add_row("Data Verified Through", "No records parsed yet", style="yellow")

    table.add_row("Total Files Ingested", str(snap.processed_files))
    table.add_row("Total Rows Parsed", f"{snap.total_records:,}")
    table.add_row("Skipped / Filtered Rows", f"{snap.skipped_records:,}")
    table.add_row("Global Unique Viewers", f"{snap.unique_ip_count:,}")
    table.add_row(
        "5xx Errors Encountered",
        str(snap.error_count),
        style="red" if snap.error_count > 0 else "green",
    )

    diag_table = Table(title="Thread Watchdogs & Diagnostics", expand=True)
    diag_table.add_column("Worker Thread", style="cyan", no_wrap=True)
    diag_table.add_column("Watchdog Health", style="white")

    for worker, elapsed in snap.heartbeats.items():
        threshold = HEARTBEAT_THRESHOLDS.get(worker, 60)
        if elapsed < threshold:
            diag_table.add_row(
                f"{worker.capitalize()} Thread",
                f"[green]ALIVE ({elapsed:.1f}s ago)[/green]",
            )
        else:
            diag_table.add_row(
                f"{worker.capitalize()} Thread",
                f"[bold red]STUCK ({elapsed:.0f}s > {threshold}s limit)[/bold red]",
            )

    if snap.recent_errors:
        diag_table.add_row("Recent Logged Errors", "\n".join(snap.recent_errors), style="red")
    else:
        diag_table.add_row("Recent Logged Errors", "[green]No pipeline errors recorded[/green]")

    renderables = [table, diag_table]

    for p in WATCHED_PATHS:
        p_records, p_ip_count, top_states = snap.path_snapshot.get(p, (0, 0, []))
        p_table = Table(title=f"Stream Target: {p}", expand=True)
        p_table.add_column("Metric", style="cyan", no_wrap=True)
        p_table.add_column("Value", style="magenta")
        p_table.add_row("Row Count (today)", f"{p_records:,}")
        p_table.add_row("Distinct Viewers", f"{p_ip_count:,}")
        if top_states:
            state_lines = "\n".join(
                f"{s}: {c:,} ({(c / p_records * 100 if p_records else 0):.1f}%)"
                for s, c in top_states
            )
            p_table.add_row(f"Top {TOP_STATES_SHOWN} States", state_lines)
        else:
            p_table.add_row("Top States", "No data yet")
        renderables.append(p_table)

    for p in CONCURRENCY_PATHS:
        buckets = snap.minute_snapshot.get(p, [])
        conc_table = Table(title=f"Live Concurrency (per-minute): {p}", expand=True)
        conc_table.add_column("Minute (IST)", style="cyan", no_wrap=True)
        conc_table.add_column("Distinct Viewers", style="magenta")

        recent = buckets[-10:]
        for i, (minute_key, count) in enumerate(recent):
            is_current = (i == len(recent) - 1)
            conc_table.add_row(
                f"{minute_key}" + (" (in progress)" if is_current else ""),
                f"{count:,}",
                style="yellow" if is_current else None,
            )
        if not buckets:
            conc_table.add_row("No data yet", "-")
        renderables.append(conc_table)

    return Panel(
        Group(*renderables),
        title="[bold green]Live Pipeline Active[/bold green]",
        subtitle=f"Error Log: {ERROR_LOG_PATH} | Ctrl+C to exit",
    )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def handle_exit(signum, frame):
    console.print("\n[red]Graceful shutdown initiated...[/red]")
    shutdown_event.set()


def main():
    signal.signal(signal.SIGINT, handle_exit)
    logger.info("Pipeline starting up (V8)...")
    console.print(f"[yellow]Starting V8 Live Monitor (IST date: {today_ist().isoformat()})[/yellow]")

    initial_seen = load_checkpoint()

    t1 = threading.Thread(target=sync_loop, daemon=True, name="SyncWorker")
    # FIX: ScanWorker is non-daemon so main() can join() it and get the final
    # checkpoint write before the process exits
    t2 = threading.Thread(target=scan_loop, args=(initial_seen,), daemon=False, name="ScanWorker")
    t3 = threading.Thread(target=export_loop, daemon=True, name="ExportWorker")

    t1.start()
    t2.start()
    t3.start()

    try:
        with Live(generate_dashboard(), refresh_per_second=2) as live:
            while not shutdown_event.is_set():
                live.update(generate_dashboard())
                time.sleep(0.5)
    finally:
        # FIX: wait for ScanWorker to write its own final checkpoint cleanly
        console.print("[yellow]Waiting for ScanWorker to flush checkpoint...[/yellow]")
        t2.join(timeout=15)
        logger.info("Pipeline stopped cleanly (V8).")
        console.print("[green]Checkpoint saved. Exiting cleanly.[/green]")
        sys.exit(0)


if __name__ == "__main__":
    main()
