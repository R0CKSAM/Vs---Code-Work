"""Isolated STREAM catch-up; verified copy to archive, without deleting inputs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ETL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ETL / "src" / "runtime"))
from etl_runtime import configure_windows_platform, worker_environment

configure_windows_platform()

import psutil
import pyarrow.parquet as pq

from archive_lake_partitions import atomic_json, copy_verified, parquet_metadata, sha256


def log(message):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def stage(env, script, output):
    if shutil.disk_usage(ETL).free < 12 * 1024**3:
        raise RuntimeError("Less than 12 GiB free; stopping before another stage.")
    log(f"Starting {output.name}")
    with output.open("w", encoding="utf-8") as handle:
        subprocess.run(
            [sys.executable, "-u", str(ETL / "src" / "pipeline" / script)],
            cwd=ETL, env=env, stdout=handle, stderr=subprocess.STDOUT, check=True,
        )
    log(f"Finished {output.name}")


def build_day(day, work, source="stream"):
    if source not in {"stream", "fast"}:
        raise ValueError("Unsupported source")
    iso = day.isoformat()
    evidence = json.loads((ETL / "output" / "state" / "downloads" / f"{iso}_{source}.json").read_text(encoding="utf-8-sig"))
    if not (evidence.get("verified") and evidence.get("status") == "complete"
            and evidence.get("date") == iso and evidence.get("source") == source
            and evidence["local_count"] == evidence["remote_count"]
            and evidence["local_bytes"] == evidence["remote_bytes"]):
        raise RuntimeError(f"No verified download checkpoint for {iso}")
    raw = Path(evidence["local_path"]).resolve()
    if not raw.is_relative_to((ETL / "data" / "raw").resolve()):
        raise RuntimeError(f"Unexpected raw location for {iso}")
    base = work / iso
    base.mkdir(parents=True, exist_ok=True)
    source_id = source + "_" + day.strftime("%Y_%m_%d")
    job = dict(source_id=source_id, source_key=source, parquet_dir=str(base / "parquet"),
               final_clean_file=str(base / f"{source_id}_final_clean.parquet"))
    env = worker_environment(dict(os.environ))
    for key in list(env):
        if key.startswith("VG_ETL_001_"):
            del env[key]
    env.pop("VG_ETL_REPLACE_DATES", None)
    env.update({
        "VG_ETL_BASE": str(base), "VG_ETL_STAGE_JOBS": json.dumps([job]),
        "VG_ETL_PROCESS_SOURCES": source_id, "VG_ETL_THREADS": "6",
        "VG_ETL_MEMORY": "8GB", "VG_ETL_DUCKDB_TEMP": str(base / "scratch"),
        "VG_ETL_DUCKDB_MAX_TEMP": "20GB", "VG_ETL_STAGE_COMPRESSION": "SNAPPY",
        "VG_ETL_COMPRESSION": "ZSTD", "VG_ETL_001_MODE": "single",
        "VG_ETL_001_INPUT_DIR": str(raw), "VG_ETL_001_OUTPUT_DIR": job["parquet_dir"],
        "VG_ETL_001_STREAMING_BATCHES": "1", "VG_ETL_001_WORKERS": "6",
        "VG_ETL_001_COMPRESSION": "snappy",
        "VG_ETL_001_PREFS_FILE": str(ETL / "output" / "state" / "gz_parquet_prefs.json"),
        "PYTHONUNBUFFERED": "1",
    })
    for script in ("001.py", "02.py", "03.py"):
        stage(env, script, work / f"{iso}_{script}.log")
    lake = base / "lake"
    parts = sorted(lake.glob(f"source={source}/year=*/month=*/day=*/part_{source_id}_*.parquet"))
    final_rows = pq.read_metadata(job["final_clean_file"]).num_rows
    lake_rows = sum(pq.read_metadata(p).num_rows for p in parts)
    if not parts or final_rows != lake_rows:
        raise RuntimeError(f"{iso}: final rows {final_rows} != lake rows {lake_rows}")
    atomic_json(base / "validated.json", dict(date=iso, final_rows=final_rows, lake_rows=lake_rows, status="validated"))
    log(f"{iso}: verified {lake_rows:,} lake rows")
    return lake


def publish(lake, archive, through, audit, source_key="stream", checkpoint=None):
    if source_key not in {"fast", "stream"}:
        raise ValueError("Unsupported source")
    for source in sorted(lake.glob(f"source={source_key}/year=*/month=*/day=*/part_*.parquet")):
        relative = source.relative_to(lake)
        values = dict(p.split("=", 1) for p in relative.parts[:-1])
        day = date(int(values["year"]), int(values["month"]), int(values["day"]))
        if day > through:
            continue
        destination = archive / relative
        if not destination.resolve().is_relative_to(archive.resolve()):
            raise RuntimeError("Archive destination escaped its root")
        record = dict(source=str(source), destination=str(destination))
        if destination.exists():
            if parquet_metadata(source) != parquet_metadata(destination) or sha256(source) != sha256(destination):
                raise RuntimeError(f"Existing archive differs; refusing overwrite: {destination}")
            record["action"] = "already_identical"
        else:
            log(f"Publishing {relative}")
            record.update(action="copied", verification=copy_verified(source, destination, verify_hash=True))
        audit.append(record)
        if checkpoint:
            checkpoint()
        log(f"Verified archive: {relative}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--recovery-pid", type=int, required=True)
    parser.add_argument("--hold-recovery", action="store_true",
                        help="Keep an already-paused recovery held after the active priority job releases its pause.")
    args = parser.parse_args()
    work, archive = args.work.resolve(), args.archive.resolve()
    if not work.is_relative_to((ETL / "output").resolve()) or not archive.is_dir():
        raise SystemExit("Work must be inside ETL/output and the archive must exist")
    work.mkdir(parents=True, exist_ok=True)
    state_file = work / "priority_state.json"
    if args.hold_recovery:
        hold_file = work / "manual_recovery_hold.json"
        if hold_file.exists():
            raise SystemExit("Manual hold already exists; do not suspend twice")
        existing = json.loads(state_file.read_text(encoding="utf-8"))
        if existing["status"] not in {"building", "validating"}:
            raise SystemExit("Priority job must still be active")
        held = []
        try:
            for item in existing["suspended"]:
                process = psutil.Process(item["pid"])
                if process.create_time() != item["created"]:
                    raise RuntimeError("Recovery PID was reused")
                # Windows suspension is reference-counted. The active coordinator
                # releases only its original hold, leaving this explicit user hold.
                process.suspend()
                held.append(process)
            atomic_json(hold_file, dict(status="held_until_user_resume", processes=existing["suspended"],
                                        created_at=datetime.now().isoformat(),
                                        reason="User requested recovery remain paused; delete nothing"))
        except BaseException:
            for process in reversed(held):
                process.resume()
            raise
        log(f"Explicit recovery hold applied: {[p.pid for p in held]}")
        return
    if state_file.exists():
        raise SystemExit("Choose a fresh work directory; existing priority state retained")
    recovery = psutil.Process(args.recovery_pid)
    if not any(v.endswith("run_recovery_pipeline.ps1") for v in recovery.cmdline()):
        raise SystemExit("PID is not the recovery runner")
    current = json.loads((ETL / "output" / "state" / "recovery_backlog.json").read_text(encoding="utf-8-sig"))
    if current.get("current_date") != "2026-10-09":
        raise SystemExit("Expected recovery on October 9; recheck before proceeding")
    state = dict(status="starting", started_at=datetime.now().isoformat(), files=[], suspended=[])
    paused = []
    try:
        # Freeze the parent first so it cannot advance to a date being staged here.
        recovery.suspend()
        paused.append(recovery)
        for process in recovery.children(recursive=True):
            if process.name().lower() in {"python.exe", "python3.13.exe", "powershell.exe"}:
                process.suspend()
                paused.append(process)
        state["suspended"] = [dict(pid=p.pid,created=p.create_time()) for p in paused]
        state["status"] = "building"
        atomic_json(state_file, state)
        log(f"Paused recovery tree: {[p.pid for p in paused]}")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(build_day, date(2026, 10, d), work) for d in (10, 11)]
            hot = ETL / "data" / "lake"
            final = ETL / "data" / "stage" / "final_clean" / "source=stream" / "year=2026" / "month=10" / "day=09" / "stream_2026_10_09_final_clean.parquet"
            parts = list(hot.glob("source=stream/year=2026/month=10/day=*/part_stream_2026_10_09_*.parquet"))
            if not parts or sum(pq.read_metadata(p).num_rows for p in parts) != pq.read_metadata(final).num_rows:
                raise RuntimeError("October 9 processed-lake row reconciliation failed")
            publish(hot, archive, date(2026, 10, 11), state["files"])
            atomic_json(state_file, state)
            for future in as_completed(futures):
                lake = future.result()
                publish(lake, archive, date(2026, 10, 11), state["files"])
                atomic_json(state_file, state)
        state["status"] = "validating"
        atomic_json(state_file, state)
        env = worker_environment(dict(os.environ, VG_ETL_BASE=str(ETL / "data")))
        for day in (9, 10, 11):
            cmd = [sys.executable, "-u", str(ETL / "src" / "tools" / "validate_daily_delivery.py"),
                   "--lake", str(archive), "--date", f"2026-10-{day:02}", "--sources", "stream",
                   "--mode", "structural", "--output-dir", str(work / "validation")]
            with (work / f"validate_{day}.log").open("w", encoding="utf-8") as handle:
                subprocess.run(cmd, env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)
        state["status"] = "complete"
        log("STREAM archive through October 11 validated; full ETL will resume")
    except BaseException as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        resumed, resume_errors = [], []
        for process in reversed(paused):
            try:
                process.resume()
                resumed.append(process.pid)
            except psutil.NoSuchProcess:
                pass
            except Exception as exc:
                resume_errors.append(dict(pid=process.pid, error=str(exc)))
        state.update(resumed=resumed, resume_errors=resume_errors, finished_at=datetime.now().isoformat())
        atomic_json(state_file, state)
        log(f"Resumed recovery PIDs: {resumed}; resume errors: {resume_errors}")


if __name__ == "__main__":
    main()
