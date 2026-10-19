"""Refresh AsRun from completed lake data, then resume the suspended recovery."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import duckdb
import psutil

from priority_stream_lake import ETL, atomic_json, log, worker_environment


def validate_identity(baseline: Path, refreshed: Path, day: str) -> list[dict]:
    with duckdb.connect() as con:
        con.execute("SET threads=2")
        # Compare rows, not just counts: unchanged history must survive intact.
        for left, right in ((baseline, refreshed), (refreshed, baseline)):
            changed = con.execute(
                "SELECT count(*) FROM ("
                "SELECT * FROM read_parquet(?) WHERE log_date <> ? EXCEPT ALL "
                "SELECT * FROM read_parquet(?) WHERE log_date <> ?)",
                [str(left), day, str(right), day],
            ).fetchone()[0]
            if changed:
                raise RuntimeError("Identity history changed outside the requested day")
        rows = con.execute(
            "SELECT source,min(minute_ist),max(minute_ist),count(DISTINCT minute_ist) "
            "FROM read_parquet(?) WHERE log_date = ? GROUP BY source",
            [str(refreshed), day],
        ).fetchall()
    if {r[0] for r in rows} != {"fast", "stream"}:
        raise RuntimeError("Missing FAST or STREAM audience data")
    for source, first, last, minutes in rows:
        if (str(first)[11:16], str(last)[11:16], minutes) != ("00:00", "23:59", 1440):
            raise RuntimeError(f"Incomplete {source} coverage: {first} to {last}, {minutes} minutes")
    return [dict(source=s, first=str(f), last=str(l), minutes=n) for s, f, l, n in rows]


def run_worker(command: list, logfile: Path, env: dict, timeout: int = 7200) -> None:
    with logfile.open("w", encoding="utf-8") as handle:
        child = subprocess.Popen([sys.executable, "-u", *map(str, command)], cwd=ETL,
                                 env=env, stdout=handle, stderr=subprocess.STDOUT)
        try:
            code = child.wait(timeout=timeout)
            if code:
                raise RuntimeError(f"Worker failed ({code}); see {logfile}")
        finally:
            if child.poll() is None:
                process = psutil.Process(child.pid)
                for descendant in reversed(process.children(recursive=True)):
                    try:
                        descendant.kill()
                    except psutil.NoSuchProcess:
                        pass
                child.kill()
                child.wait()


def publish(output: Path, destination: Path, backup: Path) -> None:
    shutil.copytree(destination, backup)
    replaced = []
    try:
        # Payloads first, HTML last. Every replacement has a recoverable backup.
        files = sorted((p for p in output.rglob("*") if p.is_file()),
                       key=lambda p: (p.suffix == ".html", str(p)))
        for source in files:
            relative = source.relative_to(output)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".priority-new")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            replaced.append(relative)
    except BaseException:
        for relative in reversed(replaced):
            saved, target = backup / relative, destination / relative
            if saved.exists():
                shutil.copy2(saved, target)
            else:
                target.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--recovery-pid", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    day, work = args.date.isoformat(), args.work.resolve()
    if not work.is_relative_to((ETL / "output/temp").resolve()) or work.exists():
        raise SystemExit("Choose a fresh directory inside ETL/output/temp")
    if shutil.disk_usage(ETL).free < 30 * 1024**3:
        raise SystemExit("Need at least 30 GiB free for isolated scratch and dashboard backup")
    recovery = psutil.Process(args.recovery_pid)
    if not any(Path(v).name.lower() in {"resume_failed_lake.ps1", "run_recovery_pipeline.ps1"}
               for v in recovery.cmdline()):
        raise SystemExit("PID does not belong to the ETL recovery launcher")
    receipt = json.loads((ETL / f"output/state/prepared_lake/{day}.json").read_text())
    if receipt.get("status") != "prepared" or receipt.get("date") != day:
        raise SystemExit("Prepared lake checkpoint is required")
    for source in ("fast", "stream"):
        for item in receipt["sources"][source]["lake"]:
            stat = Path(item["path"]).stat()
            if (stat.st_size, stat.st_mtime_ns) != (item["bytes"], item["mtime_ns"]):
                raise SystemExit("Prepared lake changed; revalidate before priority refresh")
    inputs = []
    for path in sorted((args.archive / "source=AsRUN").glob("ASRUN-*.txt")):
        parsed_day = datetime.strptime(path.stem[6:], "%d%m%y").date()
        if parsed_day <= args.date:
            inputs.append(path)
    if not any(p.name == f"ASRUN-{args.date:%d%m%y}.txt" for p in inputs):
        raise SystemExit("Requested AsRun source file is missing")
    work.mkdir(parents=True)
    state_path = work / "state.json"
    state = dict(date=day, started_at=datetime.now().isoformat(), suspended=[], resumed=[],
                 resume_errors=[], status="starting")
    paused = []

    def phase(name):
        state.update(status=name, updated_at=datetime.now().isoformat())
        atomic_json(state_path, state)
        log(name)

    try:
        # Parent-first suspension prevents the recovery from launching its next writer.
        tree = [recovery] + recovery.children(recursive=True)
        for process in tree:
            if process.name().lower() == "conhost.exe":
                continue
            if process.status() == psutil.STATUS_STOPPED:
                raise RuntimeError(f"PID {process.pid} already suspended; refusing nested hold")
            created = process.create_time()
            process.suspend()
            paused.append((process, created))
            state["suspended"].append(dict(pid=process.pid, created=created))
            phase("pausing_etl")
        phase("etl_paused")
        if psutil.virtual_memory().available < 10 * 1024**3:
            raise RuntimeError("Less than 10 GiB available; refusing an unsafe parallel memory load")
        baseline = ETL / "output/watch_hours/concurrency/identity_minute.parquet"
        audience = work / "audience"
        audience.mkdir()
        shutil.copy2(baseline, audience / baseline.name)
        env = worker_environment(dict(os.environ, VG_ETL_BASE=str(ETL / "data"),
                                      PYTHONUNBUFFERED="1"))
        for source in ("fast", "stream"):
            phase(f"identity_{source}")
            run_worker([ETL / "src/tools/build_identity_minute.py", "--source", source,
                        "--lake", ETL / "data/lake", "--archive-lake", args.archive,
                        "--start", day, "--end", day, "--out-dir", audience,
                        "--threads", "2" if source == "fast" else "4",
                        "--memory-limit", "8GB", "--temp-dir", work / "scratch" / source],
                       work / f"identity_{source}.log", env)
        phase("validating_identity")
        state["coverage"] = validate_identity(baseline, audience / baseline.name, day)
        demo = ETL / "asrun_demo"
        parsed, output = work / "parsed", work / "dashboard"
        phase("preparing_asrun")
        shutil.copytree(demo / "data/parsed", parsed)
        for kind, folder in (("YOUTUBE", "Youtube"), ("AMAGI", "amagi"),
                             ("FCT", "FCT"), ("NCT", "NCT")):
            env[f"VG_ASRUN_{kind}_ROOT"] = str(args.archive / f"source={folder}")
        phase("building_asrun")
        run_worker([demo / "src/build_asrun_demo.py", "--channel",
                    "Unassigned - stakeholder mapping required", "--identity-minute", audience / baseline.name,
                    "--parsed-dir", parsed, "--output-dir", output, "--verbose", "--input", *inputs],
                   work / "asrun_refresh.log", env)
        for relative in ("asrun_delivery_demo.html", f"data/viewer/viewer_{day}.js"):
            if not (output / relative).is_file() or not (output / relative).stat().st_size:
                raise RuntimeError(f"Required dashboard output missing: {relative}")
        phase("publishing_asrun")
        publish(output, demo / "output", work / "previous_dashboard")
        state["dashboard"] = str(demo / "output/asrun_delivery_demo.html")
        phase("complete")
    except BaseException as exc:
        state["error"] = str(exc)
        phase("failed")
        raise
    finally:
        for process, created in reversed(paused):
            try:
                if psutil.Process(process.pid).create_time() != created:
                    raise RuntimeError("PID was reused; refusing resume")
                process.resume()
                state["resumed"].append(process.pid)
            except psutil.NoSuchProcess:
                pass
            except Exception as exc:
                state["resume_errors"].append(dict(pid=process.pid, error=str(exc)))
        state["finished_at"] = datetime.now().isoformat()
        atomic_json(state_path, state)
        log(f"ETL resumed: {state['resumed']}; errors: {state['resume_errors']}")


if __name__ == "__main__":
    main()
