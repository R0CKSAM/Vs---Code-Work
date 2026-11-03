"""Automatic, space-aware VETO Parquet deduplication. Python 3.10+.

Install: python -m pip install --upgrade duckdb psutil
Run:     python veto_fast_clean.py

Pass the source master folder as the optional command-line argument, or edit
BASE_FOLDER. Source files must be finished and unchanged.
Outputs normally stay in BASE_FOLDER; when space is tight, the printed fallback
directory is used. Full-row duplicates are removed within each numbered folder.
Input schemas are combined by column name; a missing field becomes NULL so
fields first seen in later gzip-conversion parts are retained.
Completed gzip-converter pointers also locate output on other drives. Their
revision sidecars trigger an atomic rebuild when newly converted inputs arrive.
Space estimates and drive-speed rankings are heuristics, not guarantees.
"""

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

try:
    import duckdb
    import psutil
except ImportError:
    raise SystemExit("Install dependencies: python -m pip install --upgrade duckdb psutil")

BASE_FOLDER = Path(r"D:\Veto Logs Backup\Veto Stream Logs\10")
GIB, MIB = 1024 ** 3, 1024 ** 2
OWNER = "veto-space-aware-cleaner-v1"


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


def gib(value):
    return f"{value / GIB:.2f} GiB"


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
def single_run(base, lock_name=".veto_clean.lock"):
    """OS lock releases automatically after a crash; never remove the lock file."""
    handle = (base / lock_name).open("a+b")
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
        raise RuntimeError("Another process is running here, or the lock cannot be acquired.")
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
        return rank - (0.5 if self.bus == 7 else 0)  # USB is only a hint.


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
            candidates = [root / "Veto_DuckDB_Work" / job]
            for parent in (base, Path(tempfile.gettempdir())):
                try:
                    if volume(parent)[1] == identity:
                        candidates.append(parent / "Veto_DuckDB_Work" / job)
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


def cleanup_owned(parent, job, marker):
    for path in parent.glob(f".veto_{job}_*"):
        try:
            if not path.is_dir() or path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                continue
            if json.loads((path / "owner.json").read_text(encoding="utf-8")) == marker:
                shutil.rmtree(path)
                print(f"Removed unfinished work: {path}")
        except (OSError, ValueError) as exc:
            print(f"Could not clean {path}: {exc}")


def attempt_dir(parent, job, marker):
    path = parent / f".veto_{job}_{uuid.uuid4().hex}"
    path.mkdir()
    (path / "owner.json").write_text(json.dumps(marker), encoding="utf-8")
    return path


def resources():
    ram = psutil.virtual_memory()
    memory = int(min(ram.total * 0.65, ram.available * 0.80) // MIB) * MIB
    if memory < 256 * MIB:
        raise RuntimeError("Too little available RAM. Close other applications and rerun.")
    logical = psutil.cpu_count() or 1
    try:
        logical = min(logical, len(psutil.Process().cpu_affinity()))
    except (AttributeError, psutil.Error):
        pass
    physical = psutil.cpu_count(logical=False) or logical
    # Leave approximately 1 GiB of configured memory per worker when possible.
    threads = max(1, min(logical, physical, max(1, memory // GIB)))
    return memory, threads


def choose_plan(drives, base_id, output_allowance, spill_estimate, output_id=None):
    spaces = {}
    for d in drives:
        if d.writable:
            try:
                spaces[d.identity] = d.space()
            except OSError:
                pass
    drives = [d for d in drives if d.identity in spaces]
    outputs = [d for d in drives if (output_id is None or d.identity == output_id)
               and spaces[d.identity][0] - spaces[d.identity][1] >= output_allowance]
    outputs.sort(key=lambda d: (d.identity == base_id, d.speed(), spaces[d.identity][0]), reverse=True)
    for out in outputs:
        choices = []
        for temp in drives:
            free, reserve = spaces[temp.identity]
            budget = free - reserve - (output_allowance if out.identity == temp.identity else 0)
            if budget < 64 * MIB:
                continue
            # Prefer enough estimated space, then media speed and independent disks.
            different = out.disk is not None and temp.disk is not None and out.disk != temp.disk
            score = (budget >= spill_estimate, temp.speed(), different, budget)
            choices.append((score, temp, int(budget // MIB) * MIB))
        if choices:
            _, temp, budget = max(choices, key=lambda x: x[0])
            return out, temp, budget, spaces
    raise RuntimeError(f"No drive has the estimated output allowance ({gib(output_allowance)}) "
                       "plus a free-space reserve and temporary working space.")


def start_watchdog(con, drives, stop, reasons):
    def watch():
        while not stop.wait(0.5):
            try:
                for drive in drives:
                    free, reserve = drive.space()
                    if free < reserve:
                        reasons.append(f"Low free space on {drive.root}: {gib(free)} left")
                        con.interrupt()
                        return
            except OSError as exc:
                reasons.append(f"Drive unavailable: {exc}")
                con.interrupt()
                return
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


def source_pointer(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("owner") != "veto-gz-parquet-v1"
            or not Path(data.get("input_dir", "")).is_absolute()
            or Path(data["input_dir"]).resolve() != path.parent.resolve()
            or not Path(data.get("output_dir", "")).is_absolute()):
        raise RuntimeError(f"Invalid conversion pointer: {path}")
    output = Path(data["output_dir"]).resolve()
    if (data.get("complete") is not True or not isinstance(data.get("revision"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["revision"]) or not output.is_dir()):
        raise RuntimeError(f"Conversion is unfinished or unavailable; finish the converter first: {path}")
    return {"owner": OWNER, "input_dir": str(path.parent.resolve()),
            "output_dir": str(output), "revision": data["revision"]}


def discover_folders(base):
    children = list(base.iterdir())
    found = {p.name.split("_")[0]: (p, p.name.split("_")[0], None)
             for p in children if p.is_dir() and re.fullmatch(r"\d+_parquet", p.name)}
    for child in [base] + children:
        if child.is_dir() and re.fullmatch(r"\d+", child.name):
            pointer = child / ".veto_gz_state.json"
            if pointer.exists():
                source = source_pointer(pointer)  # Never fall back to old data if incomplete.
                found[child.name] = (Path(source["output_dir"]), child.name, pointer)
    return [found[k] for k in sorted(found, key=lambda k: (int(k), k))]


def signature(path):
    try:
        st = path.stat()
        return st.st_size, st.st_mtime_ns
    except FileNotFoundError:
        return None


def shard_snapshot(folder):
    return [(p.name, signature(p)) for p in sorted(folder.glob("*.parquet")) if p.is_file()]


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def process_folder(folder, base, drives, job, marker, number=None, pointer=None):
    # Share the converter's lock so a new conversion cannot start during cleaning.
    guard = single_run(pointer.parent, ".veto_gz.lock") if pointer else nullcontext()
    with guard:
        return _process_folder_locked(folder, base, drives, job, marker, number, pointer)


def _process_folder_locked(folder, base, drives, job, marker, number, pointer):
    name = (number or folder.name.split("_")[0]) + "_final_clean.parquet"
    source = source_pointer(pointer) if pointer else None
    if source and Path(source["output_dir"]) != folder.resolve():
        raise RuntimeError("Converter output location changed; restart the cleaner.")
    locations = [base / name] + [p / "outputs" / name for d in drives
                                for p in (d.known_work or (d.work,))]
    memory, threads = resources()
    con = duckdb.connect(config={"threads": threads, "memory_limit": f"{memory // MIB}MiB",
                                "preserve_insertion_order": False})
    owned, stop, reasons, monitor = [], threading.Event(), [], None
    try:
        existing_paths = list(dict.fromkeys(p for p in locations if p.exists()))
        if source and len(existing_paths) > 1:
            raise RuntimeError("Multiple final outputs exist; resolve their locations before rebuilding: "
                               + ", ".join(map(str, existing_paths)))
        previous = existing_paths[0] if existing_paths else None
        previous_signature = signature(previous) if previous else None
        for existing in existing_paths:
            matches = source is None
            if source:
                try:
                    matches = json.loads(Path(str(existing) + ".veto_source.json").read_text(
                        encoding="utf-8")) == source
                except (OSError, ValueError):
                    pass
            if matches:
                try:
                    rows = con.execute("SELECT num_rows FROM parquet_file_metadata(?)",
                                       [existing.as_posix()]).fetchone()[0]
                except duckdb.Error:
                    if source is None:
                        raise
                else:
                    print(f"SKIP existing output ({rows:,} rows): {existing}")
                    return "skipped", existing
        before = shard_snapshot(folder)
        if not before:
            if previous:
                raise RuntimeError("Source has no Parquet parts; leaving the existing final untouched.")
            print("EMPTY: no Parquet files")
            return "empty", None
        paths = [(folder / filename).as_posix() for filename, _ in before]
        source_bytes = sum(stat[0] for _, stat in before)
        raw = con.execute("SELECT coalesce(sum(total_uncompressed_size), 0) "
                          "FROM parquet_metadata(?)", [paths]).fetchone()[0]
        # Planning heuristics only: compressed input bytes are NOT an output bound.
        output_allowance = max(64 * MIB, int(source_bytes * 1.6))
        spill_estimate = max(64 * MIB, int(max(raw * 2, source_bytes * 3) - memory))
        base_id = volume(base)[1]
        pinned_id = volume(previous.parent)[1] if previous else None
        out_drive, temp_drive, spill_budget, spaces = choose_plan(
            drives, base_id, output_allowance, spill_estimate, output_id=pinned_id)
        output_parent = (previous.parent if previous else
                         base if out_drive.identity == base_id else out_drive.work / "outputs")
        output_parent.mkdir(parents=True, exist_ok=True)
        output = output_parent / name
        if previous and not os.access(previous, os.W_OK):
            raise RuntimeError(f"Existing output is read-only; leaving it untouched: {previous}")
        if not previous and output.exists():
            raise RuntimeError(f"Output appeared during processing; leaving it untouched: {output}")
        write_dir = attempt_dir(output_parent, job, marker)
        owned.append(write_dir)
        spill_dir = attempt_dir(temp_drive.work, job, marker)
        owned.append(spill_dir)
        partial = write_dir / "output.partial"
        print(f"Input: {len(paths)} files, {gib(source_bytes)} | RAM: {gib(memory)} | Threads: {threads}")
        print(f"Final output: {output}")
        print(f"Temporary drive: {temp_drive.root} ({temp_drive.kind}) | Spill cap: {gib(spill_budget)}")
        print(f"Estimated output allowance: {gib(output_allowance)} | Compression: ZSTD level 1")
        if spill_budget < spill_estimate:
            print("Space is tight: attempting with the available spill budget; estimates may be high or low.")
        con.execute(f"SET temp_directory = {quoted(spill_dir.as_posix())}")
        con.execute(f"SET max_temp_directory_size = {quoted(str(spill_budget // MIB) + 'MiB')}")
        con.execute("SET enable_progress_bar = true")
        con.execute("SET enable_progress_bar_print = true")
        watched = {d.identity: d for d in (out_drive, temp_drive)}
        monitor = start_watchdog(con, watched.values(), stop, reasons)
        try:
            rows = con.execute(
                f"COPY (SELECT DISTINCT * FROM read_parquet(?, union_by_name=true)) "
                f"TO {quoted(partial.as_posix())} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 1)", [paths],
            ).fetchone()[0]
        finally:
            stop.set()
            monitor.join()
        if reasons:
            raise RuntimeError(reasons[0])
        if source and (source_pointer(pointer) != source or shard_snapshot(folder) != before):
            raise RuntimeError("Conversion inputs changed during cleaning; leaving the final untouched.")
        if signature(output) != previous_signature:
            raise RuntimeError(f"Output changed during processing; leaving it untouched: {output}")
        partial.replace(output)  # Same-volume rename; old final remains until this succeeds.
        if source:
            atomic_json(Path(str(output) + ".veto_source.json"), source)
        print(f"DONE: {rows:,} rows | {gib(output.stat().st_size)} | {output}")
        return "written", output
    except Exception as exc:
        if reasons:
            raise RuntimeError(reasons[0]) from exc
        raise
    finally:
        stop.set()
        if monitor is not None:
            monitor.join()
        con.close()  # Close before removing spill files; next folder gets a fresh connection.
        for path in owned:
            try:
                shutil.rmtree(path)
            except OSError as exc:
                print(f"Temporary cleanup deferred until the next run: {path}: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_folder', nargs='?', type=Path, default=BASE_FOLDER,
                        help='Source master folder; defaults to BASE_FOLDER in this script')
    base = parser.parse_args().base_folder.expanduser().resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"Check BASE_FOLDER: {BASE_FOLDER}")
    folders = discover_folders(base)
    if not folders:
        print("No numbered *_parquet folders found.")
        return 0
    marker = marker_for(base)
    job = hashlib.sha256(marker["base"].encode()).hexdigest()[:16]
    counts = dict(written=0, skipped=0, empty=0, failed=0)
    start, failures = time.perf_counter(), []
    with single_run(base):
        drives = discover_drives(base, job, marker)
        work_roots = [p for d in drives for p in (d.known_work or (d.work,))]
        for parent in [base] + [p for root in work_roots for p in (root, root / "outputs")]:
            if parent.exists():
                cleanup_owned(parent, job, marker)
        print(f"DuckDB {duckdb.__version__} | {len(folders)} folders | Automatic drive/RAM/CPU selection")
        for d in drives:
            free, reserve = d.space()
            mode = "writable" if d.writable else "read-only; existing outputs only"
            print(f"Drive {d.root} | {d.kind} | Free: {gib(free)} | Reserve: {gib(reserve)} | {mode}")
        for index, (folder, number, pointer) in enumerate(folders, 1):
            print(f"\n[{index}/{len(folders)}] {folder.name}")
            began = time.perf_counter()
            try:
                status, _ = process_folder(folder, base, drives, job, marker, number, pointer)
                counts[status] += 1
            except duckdb.InterruptException:
                raise KeyboardInterrupt
            except Exception as exc:
                counts["failed"] += 1
                failures.append(folder.name)
                print(f"FAILED: {exc}")
            print(f"Folder time: {(time.perf_counter() - began) / 60:.1f} minutes")
        print("\nFinished: " + ", ".join(f"{n} {label}" for label, n in counts.items()))
        print(f"Total time: {(time.perf_counter() - start) / 60:.1f} minutes")
        if failures:
            print("Folders to retry: " + ", ".join(failures))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped. Rerun to skip completed files and restart unfinished folders.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

