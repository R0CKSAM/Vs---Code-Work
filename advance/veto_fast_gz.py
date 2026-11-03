"""Fast, resumable gzip JSONL -> Parquet, with automatic Windows resources.

Python 3.10+; run as a .py file (Windows multiprocessing needs __main__).
Install: python -m pip install --upgrade pyarrow orjson psutil tqdm
Run: python veto_fast_gz.py
Or:  python veto_fast_gz.py "D:\\Veto Logs Backup\\Veto Stream Logs\\08" --mode master

Keeps all fields except explicit drops; all data columns are strings.
Downstream DuckDB must use read_parquet(..., union_by_name=true).
Sources must be finished. Size+mtime fingerprints detect routine changes,
not deliberate changes preserving both values. Raw sources are never deleted.
"""

import argparse
import ctypes
import gzip
import hashlib
import json
import multiprocessing as mp
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

try:
    import orjson
    import psutil
    import pyarrow as pa
    import pyarrow.parquet as pq
    from tqdm import tqdm
except ImportError as exc:
    raise SystemExit("Install dependencies: python -m pip install --upgrade pyarrow orjson psutil tqdm") from exc

GIB, MIB = 1024 ** 3, 1024 ** 2
OWNER = "veto-gz-parquet-v1"
DEFAULT_INPUT = Path(r"D:\Veto Logs Backup\Veto Stream Logs\08")
PREFS_FILE = Path.home() / "gz_parquet_prefs.json"
POINTER_NAME = ".veto_gz_state.json"
BATCH_FILES = 1000
BATCH_BYTES = 64 * MIB
MAX_ROWS = 65536

def gib(value):
    return f"{value / GIB:.2f} GiB"

@lru_cache(maxsize=1)
def windows_hints():
    """Read-only discovery; unavailable or ambiguous media stays Unknown."""
    if os.name != "nt":
        return {}
    command = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { $disks = @(Get-Disk -ErrorAction Stop) } catch { $disks = @() }
try { $parts = @(Get-Partition -ErrorAction Stop) } catch { $parts = @() }
try { $physical = @(Get-PhysicalDisk -ErrorAction Stop) } catch { $physical = @() }
$rows = @(foreach ($p in $parts) {
    if (-not $p.DriveLetter) { continue }
    $d = @($disks | Where-Object { $_.Number -eq $p.DiskNumber })
    if ($d.Count -ne 1) { continue }
    $d = $d[0]; $kind = 'Unknown'; $uid = ([string]$d.UniqueId).Trim()
    if ($uid) {
        $match = @($physical | Where-Object {
            ([string]$_.UniqueId).Trim() -ceq $uid -and
            $_.UniqueIdFormat -eq $d.UniqueIdFormat
        })
        if ($match.Count -eq 1) {
            switch ([int]$match[0].MediaType) {
                3 { $kind = 'HDD' } 4 { $kind = 'SSD' } 5 { $kind = 'SCM' }
            }
        }
    }
    if ([int]$d.BusType -eq 17) { $kind = 'NVMe' }
    [pscustomobject]@{
        root = ([string]$p.DriveLetter) + ':\'; kind = $kind
        disk = [int]$d.Number; bus = [int]$d.BusType
        blocked = [bool]($d.IsReadOnly -or $d.IsOffline)
    }
})
ConvertTo-Json -InputObject $rows -Compress -Depth 3
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rows = json.loads(result.stdout.strip().lstrip("\ufeff") or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        return {r["root"].casefold(): r for r in rows}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return {}

def volume(path):
    """Return actual volume identity, including mounted volumes/junctions."""
    path = Path(path).resolve()
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        mount, name = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(128)
        for fn in (kernel.GetVolumePathNameW, kernel.GetVolumeNameForVolumeMountPointW):
            fn.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            fn.restype = wintypes.BOOL
        if not kernel.GetVolumePathNameW(str(path), mount, len(mount)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.GetVolumeNameForVolumeMountPointW(mount.value, name, len(name)):
            raise ctypes.WinError(ctypes.get_last_error())
        return Path(mount.value), name.value.casefold()
    device = path.stat().st_dev
    mount = path
    while mount.parent != mount and mount.parent.stat().st_dev == device:
        mount = mount.parent
    return mount, str(device)

@contextmanager
def single_run(base):
    """OS lock releases automatically after a crash; never remove the lock file."""
    handle = (base / ".veto_gz.lock").open("a+b")
    try:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Another conversion/cleaning process is running here, or the lock cannot be acquired.")
    try:
        yield
    finally:
        handle.close()

@dataclass
class Drive:
    root: Path
    identity: str
    work: Path
    kind: str = "Unknown"
    disk: object = None
    bus: int = 0
    known_work: tuple = ()
    writable: bool = True

    def space(self):
        usage = psutil.disk_usage(str(self.work))
        # Keep 2% free, with a 1 GiB floor and 8 GiB ceiling.
        reserve = int(min(8 * GIB, max(GIB, usage.total * 0.02)))
        return usage.free, reserve

    def speed(self):
        rank = {"NVMe": 4, "SCM": 4, "SSD": 3, "Unknown": 2, "HDD": 1}[self.kind]
        return rank - (0.5 if self.bus == 7 else 0)

def marker_for(base):
    return {"owner": OWNER, "base": os.path.normcase(str(base.resolve()))}

def own_directory(path, marker):
    path.mkdir(parents=True, exist_ok=True)
    owner = path / "owner.json"
    if owner.exists():
        if json.loads(owner.read_text(encoding="utf-8")) != marker:
            raise OSError(f"Work directory belongs to another job: {path}")
    else:
        if any(path.iterdir()):
            raise OSError(f"Unrecognized existing directory: {path}")
        with owner.open("x", encoding="utf-8") as f:
            json.dump(marker, f)
    with tempfile.TemporaryFile(dir=path) as probe:
        probe.write(b"ok")
        probe.flush()
    return path

def discover_drives(base, job, marker):
    hints, drives, seen = windows_hints(), [], set()
    paths = [base, Path(tempfile.gettempdir())]
    paths += [Path(p.mountpoint) for p in psutil.disk_partitions(all=False)]
    for path in paths:
        try:
            root, identity = volume(path)
            if identity in seen:
                continue
            if os.name == "nt":
                from ctypes import wintypes
                fixed = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
                fixed.argtypes, fixed.restype = [wintypes.LPCWSTR], wintypes.UINT
                if fixed(str(root).rstrip("\\/") + "\\") != 3:
                    continue
            hint = hints.get(str(root).casefold(), {})
            candidates = [root / "Veto_GZ_Work" / job]
            for parent in (base, Path(tempfile.gettempdir())):
                try:
                    if volume(parent)[1] == identity:
                        candidates.append(parent / "Veto_GZ_Work" / job)
                except OSError:
                    pass
            work = None
            known = []
            for candidate in candidates:
                try:
                    if json.loads((candidate / "owner.json").read_text(encoding="utf-8")) == marker:
                        if volume(candidate)[1] == identity:
                            known.append(candidate)
                except (OSError, ValueError):
                    pass
            # Keep previous readable locations even if their write permissions changed.
            candidates.sort(key=lambda p: not (p / "owner.json").exists())
            for candidate in ([] if hint.get("blocked") else candidates):
                try:
                    work = own_directory(candidate, marker)
                    if volume(work)[1] != identity:
                        work = None
                        continue
                    break
                except (OSError, ValueError):
                    work = None
                    continue
            writable = work is not None
            if work is None and not known:
                continue
            if work is None:
                work = known[0]
            if work not in known:
                known.append(work)
            drives.append(Drive(root, identity, work, hint.get("kind", "Unknown"),
                                hint.get("disk"), hint.get("bus", 0), tuple(known), writable))
            seen.add(identity)
        except (OSError, ValueError):
            continue
    if not drives:
        raise RuntimeError("No writable local drive is available for temporary files.")
    return drives


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path):
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def read_json(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return json.load(handle)


def is_link(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def output_directory_name(name):
    name = name.lower()
    return name.endswith(('_parquet', '_parqut')) or bool(
        re.search(r'_parquet_fast(?:_[0-9a-f]{16})?$', name))


def iter_gz(root):
    """Lazy discovery; no complete path list, symlink traversal or output scans."""
    stack = [Path(root)]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    name = entry.name.lower()
                    if (not output_directory_name(name)
                            and not name.startswith('.veto') and name != 'veto_gz_work'
                            and not is_link(path)):
                        stack.append(path)
                elif entry.name.lower().endswith('.gz') and entry.is_file(follow_symlinks=False):
                    info = entry.stat(follow_symlinks=False)
                    yield path.relative_to(root).as_posix(), info.st_size, info.st_mtime_ns


def has_gz(root):
    iterator = iter_gz(root)
    try:
        return next(iterator, None) is not None
    finally:
        iterator.close()


def conversion_config(drop_columns=(), add_meta=False):
    return {'format_version': 1, 'drop_columns': sorted(set(drop_columns)),
            'add_meta': bool(add_meta), 'values': 'string-or-null-v1',
            'schema_policy': 'union-by-name'}


def pointer_for(input_dir):
    path = input_dir / POINTER_NAME
    if not path.exists():
        return None
    pointer = read_json(path)
    if (pointer.get('owner') != OWNER
            or Path(pointer.get('input_dir', '')).resolve() != input_dir.resolve()):
        raise RuntimeError(f'Unrecognized state pointer: {path}')
    return pointer


def pick_output(input_dir, explicit_root, pointer, drives, job, marker):
    if explicit_root is None and pointer is not None:
        output = Path(pointer['output_dir'])
        if not output.is_dir():
            raise RuntimeError(f'Reconnect the saved output drive: {output}')
        own_directory(output, marker)
        return output.resolve()
    if explicit_root is not None:
        output = Path(explicit_root).expanduser().resolve() / (input_dir.name + '_parquet')
        own_directory(output, marker)
        return output
    choices = []
    for drive in drives:
        if drive.writable:
            free, reserve = drive.space()
            if free - reserve >= 256 * MIB:
                choices.append((drive, free - reserve))
    if not choices:
        raise RuntimeError('No writable local drive has 256 MiB above its free-space reserve.')
    largest = max(available for _, available in choices)
    # First require useful capacity, then use known media speed as a heuristic.
    viable = [(d, free) for d, free in choices if free >= max(256 * MIB, largest / 4)]
    input_volume = volume(input_dir)[1]
    viable.sort(key=lambda item: (item[0].speed(),
                item[0].identity == input_volume and item[1] >= largest / 2, item[1]), reverse=True)
    chosen, _ = viable[0]
    parent = input_dir.parent if chosen.identity == input_volume else chosen.work / 'outputs'
    for suffix in ('_parquet', '_parquet_fast', '_parquet_fast_' + job):
        output = parent / (input_dir.name + suffix)
        try:
            own_directory(output, marker)
            return output.resolve()
        except OSError:
            continue
    raise RuntimeError(f'No unused output location available under {parent}; set --output-root.')


def open_manifest(output, input_dir, config):
    directory = output / '.veto_gz_manifest'
    directory.mkdir(exist_ok=True)
    database = directory / 'inventory.sqlite3'
    if not database.exists() and any(output.glob('*.parquet')):
        raise RuntimeError(f'Existing Parquet has no trusted inventory: {output}. Use --output-root NEW_FOLDER.')
    db = sqlite3.connect(database)
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA cache_size=-16384')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL DEFAULT 'pending',
            rows INTEGER NOT NULL DEFAULT 0, parts TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY, bytes INTEGER NOT NULL, mtime INTEGER NOT NULL,
            seen INTEGER NOT NULL, batch_id INTEGER REFERENCES batches(id));
        CREATE INDEX IF NOT EXISTS files_batch ON files(batch_id);
    ''')
    identity = {'owner': OWNER, 'input_dir': str(input_dir), 'output_dir': str(output), 'config': config}
    previous = db.execute("SELECT value FROM settings WHERE key='identity'").fetchone()
    if previous is not None and json.loads(previous[0]) != identity:
        db.close()
        raise RuntimeError('Saved conversion settings differ. Reuse the original drop/meta settings, '
                           'or set --output-root NEW_FOLDER for a separate conversion.')
    with db:
        db.execute("INSERT OR IGNORE INTO settings VALUES ('identity', ?)", [json.dumps(identity)])
    return db, identity


def inventory(db, input_dir):
    """One metadata-only scan. Completed inputs are immutable; failed ones may be repaired."""
    epoch = time.time_ns()
    database_path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    count = source_bytes = 0
    with tqdm(desc='Scanning gzip files', unit='file', dynamic_ncols=True) as bar:
        try:
            for relative, size, mtime in iter_gz(input_dir):
                old = db.execute('SELECT f.bytes,f.mtime,b.status FROM files f LEFT JOIN batches b '
                                 'ON b.id=f.batch_id WHERE f.path=?', [relative]).fetchone()
                if old is None:
                    db.execute('INSERT INTO files VALUES (?,?,?,?,NULL)', [relative, size, mtime, epoch])
                else:
                    if (old[0], old[1]) != (size, mtime) and old[2] == 'done':
                        raise RuntimeError(f'Completed source changed: {relative}. '
                                           'Use --output-root NEW_FOLDER to rebuild without mixing versions.')
                    db.execute('UPDATE files SET bytes=?,mtime=?,seen=? WHERE path=?',
                               [size, mtime, epoch, relative])
                count += 1
                source_bytes += size
                bar.update(1)
                if count % 5000 == 0:
                    db.commit()
                    free, reserve = output_space(database_path.parent)
                    if free < reserve + 16 * MIB:
                        raise RuntimeError('Output drive is too full to extend the source inventory.')
            db.commit()
        except BaseException:
            db.rollback()
            raise
    missing = db.execute('SELECT path FROM files WHERE seen<>? LIMIT 1', [epoch]).fetchone()
    if missing:
        raise RuntimeError(f'Previously inventoried source is missing: {missing[0]}. Restore it, '
                           'or use --output-root NEW_FOLDER for the changed dataset.')
    # Membership is saved once. Added sources never shift an existing batch ID.
    while True:
        candidates = db.execute('SELECT path,bytes FROM files WHERE batch_id IS NULL LIMIT ?',
                                [BATCH_FILES]).fetchall()
        if not candidates:
            break
        selected, total = [], 0
        for relative, size in candidates:
            if selected and total + size > BATCH_BYTES:
                break
            selected.append((relative,))
            total += size
        with db:
            batch_id = db.execute("INSERT INTO batches(status) VALUES ('pending')").lastrowid
            db.executemany('UPDATE files SET batch_id=? WHERE path=?',
                           [(batch_id, item[0]) for item in selected])
    return count, source_bytes


def batch_records(db, batch_id):
    return db.execute('SELECT path,bytes,mtime FROM files WHERE batch_id=? ORDER BY rowid',
                      [batch_id]).fetchall()


def verify_sources(input_dir, records):
    for relative, size, mtime in records:
        _gz_check_source(input_dir / relative, relative, size, mtime)


def verify_part(path, part):
    if not path.is_file() or is_link(path) or path.stat().st_size != part['size']:
        raise RuntimeError(f'Output is missing or its size changed: {path}')
    with pq.ParquetFile(path) as parquet:
        if parquet.metadata.num_rows != part['rows'] or parquet.schema_arrow.names != part['columns']:
            raise RuntimeError(f'Output footer does not match the checkpoint: {path}')


def publish_ready(db, stage, output, input_dir, identity):
    ready = read_json(stage / 'ready.json')
    if ready.get('identity') != identity:
        raise RuntimeError(f'Staged work belongs to different settings: {stage}')
    batch_id = ready['batch_id']
    if stage.name != f'batch_{batch_id:09d}':
        raise RuntimeError(f'Unexpected stage name: {stage}')
    existing = db.execute('SELECT status,rows,parts FROM batches WHERE id=?', [batch_id]).fetchone()
    if existing is None:
        raise RuntimeError(f'Staged batch is absent from the inventory: {stage}')
    records = batch_records(db, batch_id)
    if ready.get('sources') != [list(record) for record in records]:
        raise RuntimeError(f'Staged source inventory does not match batch {batch_id}')
    verify_sources(input_dir, records)
    result = ready['result']
    if existing[0] == 'done' and (existing[1] != result['rows']
                                  or json.loads(existing[2]) != result['parts']):
        raise RuntimeError(f'Stage conflicts with the committed checkpoint: {stage}')
    if sum(part['rows'] for part in result['parts']) != result['rows']:
        raise RuntimeError(f'Invalid staged row total in {stage}')
    names = set()
    for part in result['parts']:
        name = part['name']
        if not re.fullmatch(rf'batch_{batch_id:09d}_\d{{5}}\.parquet', name) or name in names:
            raise RuntimeError(f'Unexpected or repeated staged filename: {name}')
        names.add(name)
        source, destination = stage / name, output / name
        if source.exists():
            if destination.exists():
                raise RuntimeError(f'Both staged and final files exist; refusing to replace: {destination}')
            verify_part(source, part)
            source.replace(destination)
        else:
            verify_part(destination, part)  # Resume a completed rename.
    sync_directory(output)
    sync_directory(stage)
    with db:
        db.execute("UPDATE batches SET status='done',rows=?,parts=? WHERE id=?",
                   [result['rows'], json.dumps(result['parts']), batch_id])
    # Committed work is never retried merely because removing its stage failed.
    try:
        shutil.rmtree(stage)
    except OSError as exc:
        tqdm.write(f'Checkpoint committed; stage cleanup deferred: {exc}')
    return result


def recover_stages(db, stage_root, output, input_dir, identity):
    for stage in sorted(stage_root.iterdir()):
        if stage.name == 'owner.json':
            continue
        match = re.fullmatch(r'batch_(\d{9})', stage.name)
        if not match or not stage.is_dir() or is_link(stage):
            raise RuntimeError(f'Unrecognized item in owned staging area: {stage}')
        batch_id = int(match[1])
        if db.execute('SELECT 1 FROM batches WHERE id=?', [batch_id]).fetchone() is None:
            raise RuntimeError(f'Unrecognized stage batch: {stage}')
        if (stage / 'ready.json').exists():
            print(f'Recovering publication of batch {batch_id} ...')
            publish_ready(db, stage, output, input_dir, identity)
        else:
            shutil.rmtree(stage)  # This owned, unpublished batch will be retried.


def validate_completed(db, output):
    count = rows = 0
    recorded = set()
    for status, expected_rows, encoded_parts in db.execute('SELECT status,rows,parts FROM batches'):
        if status == 'done':
            parts = json.loads(encoded_parts)
            for part in parts:
                if part['name'] in recorded:
                    raise RuntimeError('Two batches claim the same output part.')
                recorded.add(part['name'])
                verify_part(output / part['name'], part)
            if sum(p['rows'] for p in parts) != expected_rows:
                raise RuntimeError('Committed checkpoint has an inconsistent row count.')
            count += 1
            rows += expected_rows
    actual = {path.name for path in output.glob('*.parquet')}
    if actual != recorded:
        raise RuntimeError('Output folder contains untracked Parquet files. Keep this dataset separate: '
                           + ', '.join(sorted(actual - recorded)[:5]))
    return count, rows


def completion_revision(db, config):
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode())
    for row in db.execute('SELECT id,status,rows,parts FROM batches ORDER BY id'):
        if row[1] != 'done':
            raise RuntimeError('Cannot mark an incomplete conversion as complete.')
        digest.update(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode())
    return digest.hexdigest()


def automatic_resources(input_dir, drives, requested_workers=None):
    memory = psutil.virtual_memory()
    budget = int(min(memory.total * .60, memory.available * .75))
    if budget < 384 * MIB:
        raise RuntimeError('Too little available RAM. Close other applications and rerun.')
    logical = psutil.cpu_count() or 1
    try:
        logical = min(logical, len(psutil.Process().cpu_affinity()))
    except (AttributeError, psutil.Error):
        pass
    physical = min(logical, psutil.cpu_count(logical=False) or logical)
    source_id = volume(input_dir)[1]
    source_kind = next((d.kind for d in drives if d.identity == source_id), 'Unknown')
    cap = min(32, physical, max(1, budget // (768 * MIB)))
    if requested_workers is None:
        cap = min(cap, 2 if source_kind == 'HDD' else 8 if source_kind == 'Unknown' else 32)
    else:
        cap = min(cap, requested_workers)
    workers = max(1, int(cap))
    buffer_bytes = int(min(128 * MIB, max(16 * MIB, budget // workers // 8)))
    return workers, buffer_bytes, budget, source_kind


def output_space(output):
    usage = shutil.disk_usage(output)
    reserve = int(min(8 * GIB, max(GIB, usage.total * .02)))
    return usage.free, reserve


def log_failure(output, batch_id, error):
    record = {'time': datetime.now(timezone.utc).isoformat(), 'batch': batch_id, 'error': str(error)}
    try:
        with (output / 'conversion_errors.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            handle.flush()
    except OSError:
        pass
    tqdm.write(f'FAILED batch {batch_id}: {error}')


def convert_pending(db, input_dir, output, stage_root, identity, workers, buffer_bytes,
                    compression='zstd', compression_level=1):
    pending_count = db.execute("SELECT count(*) FROM batches WHERE status<>'done'").fetchone()[0]
    if not pending_count:
        return 0
    context = mp.get_context('spawn')
    stopped = context.Event()
    monitor_done = threading.Event()
    reasons = []
    free, reserve = output_space(output)
    if free - reserve < 128 * MIB:
        raise RuntimeError(f'Output drive is too full: {gib(free)} free; reserve {gib(reserve)}.')
    workers = min(workers, max(1, (free - reserve) // (buffer_bytes * 4)))

    def monitor():
        while not monitor_done.wait(.5):
            try:
                free_now, reserve_now = output_space(output)
                if free_now < reserve_now:
                    reasons.append(f'Output free space fell below {gib(reserve_now)} on {output.anchor}')
                    stopped.set()
                    return
                ram = psutil.virtual_memory()
                if ram.available < min(512 * MIB, ram.total * .03):
                    reasons.append('Available RAM became too low; completed batches are retained.')
                    stopped.set()
                    return
            except OSError as exc:
                reasons.append(f'Output drive is unavailable: {exc}')
                stopped.set()
                return

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    pool = None
    active = {}
    failures = 0
    last_id = 0
    new_rows = 0
    try:
        with tqdm(total=pending_count, desc='Converting', unit='batch', dynamic_ncols=True) as bar:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                       initializer=init_gz_worker, initargs=(stopped,))
            while True:
                while len(active) < workers and not stopped.is_set():
                    row = db.execute("SELECT id FROM batches WHERE status<>'done' AND id>? ORDER BY id LIMIT 1",
                                     [last_id]).fetchone()
                    if row is None:
                        break
                    batch_id = last_id = row[0]
                    stage = stage_root / f'batch_{batch_id:09d}'
                    stage.mkdir()  # Recovery must have removed any unfinished stage.
                    task = {'input_dir': str(input_dir), 'stage_dir': str(stage),
                            'batch_id': f'{batch_id:09d}', 'files': batch_records(db, batch_id),
                            'buffer_bytes': buffer_bytes, 'max_rows': MAX_ROWS, 'reserve_bytes': reserve,
                            'max_line_bytes': min(64 * MIB, buffer_bytes // 2),
                            'compression': compression, 'compression_level': compression_level,
                            'drop_columns': identity['config']['drop_columns'],
                            'add_meta': identity['config']['add_meta']}
                    future = pool.submit(convert_gz_batch, task)
                    active[future] = (batch_id, stage, task['files'])
                if not active:
                    break
                done, _ = wait(active, timeout=.5, return_when=FIRST_COMPLETED)
                for future in done:
                    batch_id, stage, records = active.pop(future)
                    try:
                        result = future.result()
                        for part in result['parts']:
                            with (stage / part['name']).open('r+b') as handle:
                                os.fsync(handle.fileno())
                        atomic_json(stage / 'ready.json', {'identity': identity, 'batch_id': batch_id,
                                    'sources': [list(r) for r in records], 'result': result})
                        publish_ready(db, stage, output, input_dir, identity)
                        new_rows += result['rows']
                    except Exception as exc:
                        failures += 1
                        stopped.set()
                        log_failure(output, batch_id, exc)
                        # A ready journal may already have promoted some files. Keep it.
                        if not (stage / 'ready.json').exists():
                            try:
                                shutil.rmtree(stage)
                            except OSError:
                                pass
                    bar.update(1)
                    bar.set_postfix(rows=f'{new_rows:,}', failed=failures, refresh=False)
            if reasons:
                raise RuntimeError(reasons[0])
            if failures:
                raise RuntimeError(f'{failures} batch(es) failed/cancelled. Fix the reported cause and rerun; '
                                   'completed batches will be skipped.')
    finally:
        stopped.set()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        monitor_done.set()
        thread.join()
    return new_rows


def process_input(input_dir, explicit_root=None, drops=None, add_meta=None,
                  workers=None, compression='zstd', compression_level=1):
    input_dir = Path(input_dir).expanduser().resolve()
    with single_run(input_dir):
        pointer = pointer_for(input_dir)
        saved = pointer.get('config', {}) if pointer else {}
        config = conversion_config(saved.get('drop_columns', []) if drops is None else drops,
                                   saved.get('add_meta', False) if add_meta is None else add_meta)
        marker = marker_for(input_dir)
        job = hashlib.sha256((OWNER + str(input_dir)).encode()).hexdigest()[:16]
        drives = discover_drives(input_dir, job, marker)
        output = pick_output(input_dir, explicit_root, pointer, drives, job, marker)
        db, identity = open_manifest(output, input_dir, config)
        stage_key = hashlib.sha256(str(output).encode()).hexdigest()[:16]
        stage_root = output.parent / ('.veto_gz_stage_' + stage_key)
        try:
            own_directory(stage_root, marker)
            if volume(stage_root)[1] != volume(output)[1]:
                raise RuntimeError('Staging and output must be on the same volume.')
            active_pointer = dict(identity, complete=False, revision=None)
            atomic_json(input_dir / POINTER_NAME, active_pointer)
            print(f'\nInput : {input_dir}\nOutput: {output}')
            for drive in drives:
                free, reserve = drive.space()
                print(f'Drive {drive.root}: {drive.kind}; {gib(free)} free; {gib(reserve)} reserved')
            recover_stages(db, stage_root, output, input_dir, identity)
            count, source_bytes = inventory(db, input_dir)
            completed, old_rows = validate_completed(db, output)
            worker_count, buffer_bytes, budget, source_kind = automatic_resources(input_dir, drives, workers)
            print(f'{count:,} gzip files; {gib(source_bytes)} compressed; {completed:,} completed batches')
            print(f'Workers: {worker_count} | RAM planning budget: {gib(budget)} | '
                  f'Buffer per worker: {buffer_bytes // MIB} MiB | Source media: {source_kind}')
            print(f'Compression: {compression}' + (f' level {compression_level}' if compression == 'zstd' else ''))
            print(f'Dropped columns: {", ".join(config["drop_columns"]) or "none"}; new fields are kept')
            started = time.perf_counter()
            new_rows = convert_pending(db, input_dir, output, stage_root, identity,
                                       worker_count, buffer_bytes, compression, compression_level)
            revision = completion_revision(db, config)
            atomic_json(input_dir / POINTER_NAME, dict(identity, complete=True, revision=revision))
            print(f'COMPLETE: {old_rows + new_rows:,} total rows; {new_rows:,} newly written; '
                  f'{(time.perf_counter() - started) / 60:.1f} processing minutes')
            print(f'Parquet folder: {output}')
            return output
        finally:
            db.close()


def sample_columns(folders, max_files=8, max_rows=500, max_bytes=8 * MIB):
    """Small display-only sample. It never decides which unseen fields survive."""
    columns = set()
    sampled = 0
    for folder in folders:
        iterator = iter_gz(folder)
        try:
            item = next(iterator, None)
        finally:
            iterator.close()
        if item is None:
            continue
        relative = item[0]
        try:
            used = 0
            with gzip.open(folder / relative, 'rb') as handle:
                for _ in range(max_rows):
                    raw = handle.readline(max_bytes - used + 1)
                    used += len(raw)
                    if not raw or used > max_bytes:
                        break
                    obj = orjson.loads(raw)
                    if isinstance(obj, dict):
                        columns.update(obj)
        except (OSError, EOFError, ValueError) as exc:
            print(f'Sample unavailable for {relative}: {exc}. Full conversion will validate it.')
        sampled += 1
        if sampled >= max_files:
            break
    return sorted(columns)


def choose_columns(folders):
    saved = read_json(PREFS_FILE) if PREFS_FILE.exists() else {}
    dropped = set(saved.get('cols_to_drop', []))
    columns = sample_columns(folders)
    print('\nColumn sample is for selection only. Every unseen field is kept.')
    if dropped:
        print('Saved drops: ' + ', '.join(sorted(dropped)))
    for number, name in enumerate(columns, 1):
        print(f'{number:4}: {name}' + (' [DROP]' if name in dropped else ''))
    print('Enter numbers to toggle drops, "reset" to keep all, or Enter to finish.')
    while True:
        raw = input('Columns > ').strip()
        if not raw or raw.lower() == 'done':
            break
        if raw.lower() == 'reset':
            dropped.clear()
            print('All columns will be kept.')
            continue
        try:
            numbers = [int(value) for value in re.split(r'[\s,]+', raw)]
            if any(number < 1 or number > len(columns) for number in numbers):
                raise ValueError
        except ValueError:
            print('Use the displayed column numbers, separated by spaces or commas.')
            continue
        for number in numbers:
            name = columns[number - 1]
            if name in dropped:
                dropped.remove(name)
            else:
                dropped.add(name)
        print('Dropped: ' + (', '.join(sorted(dropped)) or 'none'))
    atomic_json(PREFS_FILE, {'cols_to_drop': sorted(dropped),
                           'saved_at': datetime.now(timezone.utc).isoformat()})
    return sorted(dropped)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input_dir', nargs='?', help='Source folder or master folder containing day folders')
    parser.add_argument('--mode', choices=['master', 'single'], default=None)
    parser.add_argument('--output-root', type=Path, help='Optional fixed parent for <source>_parquet outputs')
    parser.add_argument('--drop', action='append', default=None, help='Exact column name to drop; repeat for more')
    parser.add_argument('--keep-all', action='store_true', help='Explicitly keep all fields; overrides saved drops')
    parser.add_argument('--select-columns', action='store_true', help='Show the interactive column menu')
    parser.add_argument('--src-file', action='store_true', default=None, help='Add source basename as _src_file')
    parser.add_argument('--workers', type=int, help='Optional worker ceiling; still bounded by available RAM/CPU')
    parser.add_argument('--compression', choices=['zstd', 'snappy', 'lz4', 'none'], default='zstd')
    parser.add_argument('--level', type=int, default=1, help='ZSTD level 1..22 (default 1 for speed)')
    args = parser.parse_args()
    if args.workers is not None and args.workers < 1:
        parser.error('--workers must be positive')
    if not 1 <= args.level <= 22:
        parser.error('--level must be between 1 and 22')
    if args.keep_all and args.drop:
        parser.error('Choose --keep-all or --drop, not both')
    interactive = args.input_dir is None
    if interactive:
        print('Gzip JSONL -> Parquet | automatic CPU, RAM and drive selection')
        raw = input(f'Input/master folder [{DEFAULT_INPUT}]: ').strip().strip('\"\'')
        args.input_dir = raw or str(DEFAULT_INPUT)
        if args.mode is None:
            answer = input('Mode: 1=single folder, 2=master with day folders [2]: ').strip()
            args.mode = 'single' if answer == '1' else 'master'
    root = Path(args.input_dir).expanduser().resolve()
    if not root.is_dir():
        parser.error(f'Input directory does not exist: {root}')
    mode = args.mode or 'master'
    if mode == 'single':
        folders = [root]
    else:
        folders = sorted((p for p in root.iterdir() if p.is_dir() and not is_link(p)
                          and not output_directory_name(p.name)
                          and not p.name.startswith('.') and p.name.lower() != 'veto_gz_work'
                          and (has_gz(p) or (p / POINTER_NAME).exists())),
                         key=lambda p: (0, int(p.name)) if p.name.isdigit() else (1, p.name))
    if not folders:
        print('No source folders containing .gz files were found.')
        return 0
    drops = [] if args.keep_all else args.drop
    if args.select_columns:
        drops = choose_columns(folders)
    elif interactive and not any((folder / POINTER_NAME).exists() for folder in folders):
        if input('Select columns to drop? [y/N]: ').strip().lower() in {'y', 'yes'}:
            drops = choose_columns(folders)
    print(f'Folders: {len(folders)}. Existing settings and output locations are reused on resume.')
    failures = []
    for index, folder in enumerate(folders, 1):
        print(f'\n[{index}/{len(folders)}] {folder.name}')
        try:
            process_input(folder, args.output_root, drops, args.src_file, args.workers,
                          args.compression, args.level)
        except Exception as exc:
            failures.append(folder.name)
            print(f'FAILED {folder.name}: {exc}')
            # A capacity/write error must not start another folder on the same full disk.
            break
    if failures:
        print('Stopped with unfinished work. Rerun the same command after fixing the reported cause.')
        return 1
    print('\nAll selected folders completed. Keep the state files for reliable resume.')
    print('Next step: use veto_fast_clean.py with BASE_FOLDER set to the source master folder.')
    return 0


"""Worker fragment for the Veto gzip JSONL converter.

The parent owns inventory, scheduling, stage cleanup, promotion, and checkpoints.
Each task must receive its own existing, empty stage directory on the output
volume. No source or final-output file is changed by this module.
"""

import errno
import gzip
import io
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq


_STOP = None


class ConversionError(RuntimeError):
    """A complete conversion batch must be retried; no result was committed."""


def init_gz_worker(stop_event):
    """Run once in each ProcessPoolExecutor child."""
    global _STOP
    _STOP = stop_event
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)


def _gz_check_stop():
    if _STOP is not None and _STOP.is_set():
        raise ConversionError("Stopped because another batch failed or the run was cancelled.")


def _gz_stop_for_space():
    if _STOP is not None:
        _STOP.set()


def _gz_disk_full(exc):
    """Arrow can expose an OS write failure without preserving errno."""
    if getattr(exc, "errno", None) == errno.ENOSPC:
        return True
    if getattr(exc, "winerror", None) == 112:
        return True
    message = str(exc).lower()
    return "no space left on device" in message or "disk is full" in message


def _gz_short_error(exc, limit=600):
    text = str(exc).replace("\n", " ").replace("\r", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def _gz_check_source(path, relative, expected_size, expected_mtime_ns):
    """lstat semantics: reject a symlink or other nonregular source file."""
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ConversionError(f"{relative}: source is not a regular, nonsymlink file.")
    if info.st_size != expected_size or info.st_mtime_ns != expected_mtime_ns:
        raise ConversionError(
            f"{relative}: source changed since inventory "
            f"(expected size={expected_size}, mtime_ns={expected_mtime_ns}; "
            f"found size={info.st_size}, mtime_ns={info.st_mtime_ns})."
        )
    return info


def _gz_same_file(left, right):
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _gz_normalize(obj, dropped, add_meta, source_name):
    """Preserve original scalar, nested JSON, and placeholder semantics.

    The estimate deliberately counts repeated key/value strings again. It is a
    conservative buffer target, not a hard limit on the process's total RAM.
    """
    row = {}
    estimated_bytes = 8  # Pointer in the buffer's list.
    for key, value in obj.items():
        if key in dropped:
            continue
        if add_meta and key == "_src_file":
            raise ConversionError(
                "Input already contains a retained '_src_file' field; disable "
                "source metadata or explicitly drop that input field."
            )
        if value is None:
            rendered = None
        elif isinstance(value, (dict, list)):
            rendered = orjson.dumps(value).decode("utf-8")
        else:
            rendered = str(value)
            if rendered == "-" or rendered == "^":
                rendered = None
        row[key] = rendered
        estimated_bytes += sys.getsizeof(key)
        if rendered is not None:
            estimated_bytes += sys.getsizeof(rendered)
    if add_meta:
        row["_src_file"] = source_name
        estimated_bytes += sys.getsizeof("_src_file") + sys.getsizeof(source_name)
    estimated_bytes += sys.getsizeof(row)
    return row, estimated_bytes


def convert_gz_batch(task):
    """Convert one immutable inventory batch into staged Parquet parts.

    Required task keys:
      input_dir, stage_dir, batch_id, files [(relative, size, mtime_ns)],
      buffer_bytes, max_rows, reserve_bytes.
    Optional keys:
      drop_columns=(), add_meta=False, compression='zstd',
      compression_level=1, max_line_bytes=64*1024*1024.

    Schema expands only at a buffer boundary, starting another part if needed.
    Consumers MUST use read_parquet(..., union_by_name=true). A successful return
    is a verified manifest; a raised exception means discard this entire stage.
    """
    started = time.monotonic()
    batch_id = str(task["batch_id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
        raise ConversionError("batch_id must contain only letters, digits, '_' or '-'.")
    input_dir = Path(task["input_dir"])
    stage_dir = Path(task["stage_dir"])
    records = task["files"]
    dropped = frozenset(task.get("drop_columns", ()))
    add_meta = bool(task.get("add_meta", False))
    compression = str(task.get("compression", "zstd")).lower()
    compression_level = task.get("compression_level", 1)
    buffer_limit = int(task["buffer_bytes"])
    max_rows = int(task["max_rows"])
    reserve_bytes = int(task["reserve_bytes"])
    max_line_bytes = int(task.get("max_line_bytes", 64 * 1024 * 1024))
    if buffer_limit <= 0 or max_rows <= 0 or max_line_bytes <= 0 or reserve_bytes < 0:
        raise ConversionError("Buffer/row/line limits must be positive; reserve cannot be negative.")
    if not stage_dir.is_dir() or stage_dir.is_symlink():
        raise ConversionError(f"Stage must be an existing nonsymlink directory: {stage_dir}")
    if next(stage_dir.iterdir(), None) is not None:
        raise ConversionError(f"Stage must be empty before conversion: {stage_dir}")

    buffer = []
    buffer_keys = set()
    buffer_size = 0
    writer = None
    writer_schema = None
    writer_columns = []
    writer_key_set = set()
    part_path = None
    part_rows = 0
    parts = []
    total_rows = 0
    total_input_bytes = 0
    input_count = 0
    location = "batch setup"
    line_number = 0

    def check_space():
        free = shutil.disk_usage(stage_dir).free
        if free <= reserve_bytes:
            _gz_stop_for_space()
            raise ConversionError(
                f"Output drive reached its free-space reserve: "
                f"free={free / (1024 ** 3):.2f} GiB, "
                f"reserve={reserve_bytes / (1024 ** 3):.2f} GiB."
            )

    def close_part():
        nonlocal writer, part_rows, part_path
        if writer is None:
            return
        check_space()
        writer.close()
        writer = None
        with pq.ParquetFile(part_path) as parquet_file:
            meta = parquet_file.metadata
            observed_rows = int(meta.num_rows)
            if observed_rows != part_rows:
                raise ConversionError(
                    f"{part_path.name}: metadata has {observed_rows} rows; "
                    f"expected {part_rows}."
                )
            if not parquet_file.schema_arrow.equals(writer_schema, check_metadata=False):
                raise ConversionError(f"{part_path.name}: written schema failed verification.")
        output_size = part_path.stat().st_size
        if output_size <= 0:
            raise ConversionError(f"{part_path.name}: output is empty after close.")
        parts.append({
            "name": part_path.name,
            "rows": part_rows,
            "size": output_size,
            "columns": list(writer_columns),
        })
        part_path = None
        part_rows = 0

    def flush_buffer():
        nonlocal writer, writer_schema, writer_columns, writer_key_set
        nonlocal part_path, part_rows, buffer_size
        if not buffer:
            return
        _gz_check_stop()
        check_space()
        expanded = buffer_keys - writer_key_set
        if writer is None or expanded:
            close_part()
            writer_key_set.update(buffer_keys)
            writer_columns = sorted(writer_key_set)
            if not writer_columns:
                raise ConversionError(
                    f"{len(buffer)} buffered records have no retained columns. "
                    "Enable source metadata or retain at least one input field; "
                    "zero-column records cannot be written without losing their row count."
                )
            writer_schema = pa.schema([(name, pa.string()) for name in writer_columns])
            part_path = stage_dir / f"batch_{batch_id}_{len(parts) + 1:05d}.parquet"
            if part_path.exists():
                raise ConversionError(f"Refusing to replace staged output: {part_path.name}")
            options = {"compression": compression, "use_dictionary": True}
            if compression == "zstd":
                options["compression_level"] = int(compression_level)
            writer = pq.ParquetWriter(part_path, writer_schema, **options)
        # Explicit schema includes every retained key from every buffered row.
        # Arrow supplies nulls for missing fields, so no second list of row dicts
        # is needed. Schema discovery must not rely on from_pylist's first row.
        table = pa.Table.from_pylist(buffer, schema=writer_schema)
        writer.write_table(table, row_group_size=max_rows)
        part_rows += len(buffer)
        del table
        buffer.clear()
        buffer_keys.clear()
        buffer_size = 0

    try:
        _gz_check_stop()
        check_space()
        for relative, expected_size, expected_mtime_ns in records:
            _gz_check_stop()
            relative = str(relative)
            relative_path = Path(relative)
            if relative_path.is_absolute() or relative_path.drive or ".." in relative_path.parts:
                raise ConversionError(f"Invalid source-relative path: {relative}")
            location = relative
            line_number = 0
            source = input_dir / relative_path
            source_name = source.name
            expected_size = int(expected_size)
            expected_mtime_ns = int(expected_mtime_ns)
            before = _gz_check_source(source, relative, expected_size, expected_mtime_ns)
            # gzip verifies trailer/CRC while reading to EOF. A corrupt file
            # fails the whole batch, including rows buffered before that error.
            with source.open("rb") as compressed:
                opened = os.fstat(compressed.fileno())
                if not _gz_same_file(before, opened):
                    raise ConversionError(f"{relative}: source changed while being opened.")
                with gzip.GzipFile(fileobj=compressed, mode="rb") as decompressor:
                    with io.BufferedReader(decompressor, buffer_size=1024 * 1024) as lines:
                        while True:
                            if line_number % 256 == 0:
                                _gz_check_stop()
                            line = lines.readline(max_line_bytes + 1)
                            if not line:
                                break
                            line_number += 1
                            if len(line) > max_line_bytes:
                                raise ConversionError(
                                    f"JSONL line exceeds max_line_bytes={max_line_bytes}; "
                                    "increase the configured line limit only if expected."
                                )
                            if line.isspace():
                                continue
                            obj = orjson.loads(line)
                            if not isinstance(obj, dict):
                                raise ConversionError("Expected a JSON object on each nonblank line.")
                            row, row_size = _gz_normalize(obj, dropped, add_meta, source_name)
                            del obj, line
                            if row_size > buffer_limit:
                                raise ConversionError(
                                    f"One converted record needs approximately {row_size} buffer bytes, "
                                    f"exceeding buffer_bytes={buffer_limit}."
                                )
                            if buffer and (buffer_size + row_size > buffer_limit or len(buffer) >= max_rows):
                                flush_buffer()
                            buffer.append(row)
                            buffer_keys.update(row)
                            buffer_size += row_size
                            total_rows += 1
                            del row
                            if len(buffer) >= max_rows:
                                flush_buffer()
                after_handle = os.fstat(compressed.fileno())
                if not _gz_same_file(opened, after_handle):
                    raise ConversionError(f"{relative}: source changed during conversion.")
            after = _gz_check_source(source, relative, expected_size, expected_mtime_ns)
            if not _gz_same_file(before, after):
                raise ConversionError(f"{relative}: source was replaced during conversion.")
            input_count += 1
            total_input_bytes += expected_size
        _gz_check_stop()
        flush_buffer()
        close_part()
        if sum(part["rows"] for part in parts) != total_rows:
            raise ConversionError("Batch metadata row total does not match the parsed record count.")
        _gz_check_stop()
        return {
            "batch_id": batch_id,
            "status": "ok" if total_rows else "empty",
            "rows": total_rows,
            "input_files": input_count,
            "input_bytes": total_input_bytes,
            "output_bytes": sum(part["size"] for part in parts),
            "columns": list(writer_columns),
            "parts": parts,
            "elapsed_sec": round(time.monotonic() - started, 3),
        }
    except Exception as exc:
        if _gz_disk_full(exc):
            _gz_stop_for_space()
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        where = f"{location}, line {line_number}" if line_number else location
        raise ConversionError(
            f"Batch {batch_id}, {where}: {type(exc).__name__}: {_gz_short_error(exc)}"
        ) from exc



if __name__ == '__main__':
    mp.freeze_support()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nStopped. Completed batches are retained; rerun to continue.')
        raise SystemExit(130)
    except Exception as exc:
        print(f'ERROR: {exc}')
        raise SystemExit(1)
