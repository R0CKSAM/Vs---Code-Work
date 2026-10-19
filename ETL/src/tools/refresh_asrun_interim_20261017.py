"""Publish the validated October 17 AsRun while October 18 is rebuilding."""

from datetime import datetime
import json
import os
from pathlib import Path
import shutil

import duckdb
import psutil

from refresh_asrun_priority import ETL, atomic_json, log, publish, run_worker, worker_environment


def main():
    day = "2026-10-17"
    work = ETL / "output/temp" / ("asrun_interim_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    work.mkdir()
    state = dict(status="starting", through=day, work=str(work))
    state_path = work / "state.json"

    def phase(name):
        state.update(status=name, updated_at=datetime.now().isoformat())
        atomic_json(state_path, state)
        log(f"{name}: {work}")

    try:
        baseline = ETL / "output/watch_hours/concurrency/identity_minute.parquet"
        with duckdb.connect() as con:
            con.execute("SET threads=2")
            rows = con.execute(
                "SELECT source,count(DISTINCT minute_ist) FROM read_parquet(?) "
                "WHERE log_date = ? GROUP BY source", [str(baseline), day]).fetchall()
        if dict(rows) != {"fast": 1440, "stream": 1440}:
            raise RuntimeError("October 17 full-day audience coverage is required")
        demo = ETL / "asrun_demo"
        archive = Path(r"Z:\Veto Logs Backup\DO NOT DELETE")
        inputs = [p for p in sorted((archive / "source=AsRUN").glob("ASRUN-*.txt"))
                  if datetime.strptime(p.stem[6:], "%d%m%y").date().isoformat() <= day]
        if not any(p.name == "ASRUN-171026.txt" for p in inputs):
            raise RuntimeError("October 17 AsRun source missing")
        phase("preparing")
        parsed, output = work / "parsed", work / "dashboard"
        shutil.copytree(demo / "data/parsed", parsed)
        env = worker_environment(dict(os.environ, PYTHONUNBUFFERED="1"))
        for kind, folder in (("YOUTUBE", "Youtube"), ("AMAGI", "amagi"), ("FCT", "FCT"), ("NCT", "NCT")):
            env[f"VG_ASRUN_{kind}_ROOT"] = str(archive / f"source={folder}")
        phase("building")
        run_worker([demo / "src/build_asrun_demo.py", "--channel",
                    "Unassigned - stakeholder mapping required", "--identity-minute", baseline,
                    "--parsed-dir", parsed, "--output-dir", output, "--verbose", "--input", *inputs],
                   work / "build.log", env)
        for relative in ("asrun_delivery_demo.html", f"data/viewer/viewer_{day}.js"):
            if not (output / relative).is_file() or not (output / relative).stat().st_size:
                raise RuntimeError(f"Required output missing: {relative}")

        # Hold only the priority coordinator during publication, never its worker.
        # This prevents the older interim build overwriting a newer completed build.
        priority_state = ETL / "output/temp/asrun_priority_20261019_171159/state.json"
        coordinator = None
        try:
            try:
                candidate = psutil.Process(3712)
                if any(Path(arg).name == "refresh_asrun_priority.py" for arg in candidate.cmdline()):
                    if candidate.status() == psutil.STATUS_STOPPED:
                        raise RuntimeError("Priority coordinator is already held")
                    candidate.suspend()
                    coordinator = candidate
            except psutil.NoSuchProcess:
                pass
            priority = json.loads(priority_state.read_text())
            if priority["status"] in {"building_asrun", "publishing_asrun", "complete"}:
                phase("ready_but_newer_refresh_takes_priority")
                return
            phase("publishing")
            publish(output, demo / "output", work / "previous_dashboard")
        finally:
            if coordinator is not None:
                coordinator.resume()
        state["dashboard"] = str(demo / "output/asrun_delivery_demo.html")
        phase("complete")
    except BaseException as exc:
        state["error"] = str(exc)
        phase("failed")
        raise


if __name__ == "__main__":
    main()
