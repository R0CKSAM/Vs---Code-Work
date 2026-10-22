"""Build one downloaded raw day through validated lake, without publishing dashboards."""
import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from check_raw_delivery import IST, atomic_json
from cleanup_daily_intermediates import source_lake_rows, etl_state_rows, load_validation_report
from recovery_capacity_guard import check_capacity

ETL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ETL / "src/orchestrator"))
from run_pipeline import _process_is_running, PipelineRunLock
sys.path.insert(0, str(ETL / "src/runtime"))
from etl_notifications import notify_failure


def verified_download(path, day, source, not_before):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not (data.get("status") == "complete" and data.get("verified") is True
            and data.get("date") == day and data.get("source") == source
            and data.get("local_count", 0) > 0 and data.get("local_count") == data.get("remote_count")
            and data.get("local_bytes") == data.get("remote_bytes")
            and datetime.fromisoformat(data["finished_at_ist"]) >= not_before):
        raise RuntimeError(f"No fresh verified download for {source} {day}")


def wait_for_repair(path, timeout=7 * 86400):
    print(f"Waiting for historical repair: {path}", flush=True)
    deadline = time.monotonic() + timeout
    while True:
        repair = json.loads(path.read_text(encoding="utf-8-sig"))
        status = repair.get("status")
        if status == "core_repair_complete_external_asrun_pending":
            return
        if status == "failed":
            raise RuntimeError("Historical repair failed; retaining downloaded inputs")
        if time.monotonic() >= deadline:
            raise RuntimeError("Historical repair wait exceeded timeout")
        time.sleep(15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--download-pid", required=True, type=int)
    parser.add_argument("--download-started", required=True, type=datetime.fromisoformat)
    parser.add_argument("--wait-for-repair", type=Path,
                        help="Wait for historical repair completion before claiming lake priority.")
    parser.add_argument("--archive", type=Path, default=Path(r"Z:\Veto Logs Backup\DO NOT DELETE"))
    args = parser.parse_args()
    if args.date >= datetime.now(IST).date() or args.download_started.tzinfo is None:
        parser.error("Use a past date and timezone-aware download start")
    day = str(args.date)
    base = ETL / "data"
    work = ETL / "output/temp" / ("core_lake_" + day)
    work.mkdir(parents=True, exist_ok=True)
    if args.wait_for_repair:
        wait_for_repair(args.wait_for_repair)
    import msvcrt
    owner = (ETL / "output/state/core_lake_priority.lock").open("a+b")
    owner.seek(0)
    msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
    request_path = ETL / "output/state/core_lake_priority.json"
    name = "core_lake_" + day.replace("-", "")
    state = dict(date=day, pid=os.getpid(), state_names=[name], status="downloading",
                 dashboard_status="pending", completed=False)

    def save(status):
        state.update(status=status, updated_at=datetime.now(IST).isoformat())
        atomic_json(request_path, state)
        atomic_json(work / "state.json", state)

    def run(label, command, env):
        print(f"{datetime.now(IST).isoformat()} START {label}", flush=True)
        state["step"] = label
        state["log"] = str(work / f"{label}.log")
        save(state["status"])
        with Path(state["log"]).open("a", encoding="utf-8") as log:
            subprocess.run(command, cwd=ETL, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    save("downloading")
    try:
        deadline = time.monotonic() + 24 * 3600
        while _process_is_running(args.download_pid):
            if time.monotonic() >= deadline:
                raise RuntimeError("Download wait exceeded 24 hours")
            time.sleep(15)
        for source in ("fast", "stream"):
            verified_download(ETL / "output/state/downloads" / f"{day}_{source}.json", day, source, args.download_started)
        print(json.dumps(check_capacity(base, args.archive, 20, 100)), flush=True)
        scratch = args.archive / "Temp/VetoETL/duckdb/core_lake"
        final = args.archive / "Temp/VetoETL/final_clean"
        env = os.environ.copy()
        env.update(VG_ETL_FINAL_CLEAN_ROOT=str(final), VG_DUCKDB_TEMP_DIR=str(scratch),
                   VG_ETL_ARCHIVE_LAKE_ROOTS=str(args.archive))
        command = [sys.executable, "-u", str(ETL / "src/orchestrator/run_pipeline.py"),
                   "--base", str(base), "--archive-lake", str(args.archive), "--state-name", name,
                   "--etl1-daily-date", day, "--etl1-workers", "8", "--stage-threads", "12",
                   "--stage-memory", "16GB", "--stage-max-temp-size", "100GB",
                   "--deep-profile-temp-dir", str(scratch), "--deep-profile-max-temp-size", "100GB"]
        command += ["--skip-" + step for step in ("watch", "overview", "deep-profile", "device-snapshot",
                    "device-decode-profile", "concurrency", "latency", "identity-mart", "content-mart", "audience", "master")]
        save("waiting")
        run("core_pipeline", command, env)
        save("cleaning")
        # Retain the priority lease and acquire the shared lock during validation/retirement.
        lock = PipelineRunLock(ETL / "output")
        lock.acquire()
        try:
            validation_dir = work / "validation"
            run("validate_lake", [sys.executable, str(ETL / "src/tools/validate_daily_delivery.py"),
                "--lake", str(base / "lake"), "--archive-lake", str(args.archive), "--date", day,
                "--mode", "structural", "--output-dir", str(validation_dir)], env)
            report = validation_dir / "daily_delivery_validation_latest.json"
            load_validation_report(report, day, ["fast", "stream"], allow_lake_only=True)
            receipt = dict(status="lake_ready", date=day, sources={}, dashboard_status="pending")
            for source in ("fast", "stream"):
                source_id = source + "_" + day.replace("-", "_")
                expected = etl_state_rows(base / ".etl_03_state.json", source, source_id)
                rows, files = source_lake_rows([base / "lake", args.archive], source, source_id, args.date)
                if expected != rows:
                    raise RuntimeError(f"{source} batch/lake row mismatch; retaining all inputs")
                checkpoint = ETL / "output/state/downloads" / f"{day}_{source}.json"
                receipt["sources"][source] = dict(rows=rows,
                    download_checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                    lake=[dict(path=str(p.resolve()), bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in files])
            atomic_json(ETL / "output/state/prepared_lake" / f"{day}.json", receipt)
            run("cleanup", [sys.executable, str(ETL / "src/tools/cleanup_daily_intermediates.py"),
                "--base", str(base), "--lake", str(base / "lake"), "--archive-lake", str(args.archive),
                "--raw-root", str(base / "raw/Veto Logs Backup"), "--date", day,
                "--final-clean-root", str(final), "--etl3-state", str(base / ".etl_03_state.json"),
                "--validation-report", str(report), "--allow-lake-only-validation",
                "--audit-dir", str(work / "cleanup"), "--execute"], env)
        finally:
            lock.release()
        state["completed"] = True
        save("lake_ready")
        print(f"{day}: lake validated, inputs retired; dashboards still pending.", flush=True)
    except BaseException as exc:
        state["error"] = str(exc)
        save("failed")
        notify_failure("Core lake priority", str(exc), state.get("log"), work / "state.json")
        raise


if __name__ == "__main__":
    main()
