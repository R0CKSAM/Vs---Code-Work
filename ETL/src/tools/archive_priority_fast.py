"""Queue a verified, copy-only FAST archive after the ASRUN priority refresh."""

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from priority_stream_lake import ETL, atomic_json, log, publish, worker_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    work, archive = args.work.resolve(), args.archive.resolve()
    if not work.is_relative_to((ETL / "output").resolve()) or not archive.is_dir():
        raise SystemExit("Expected existing priority work and archive directories")
    state_path = work / "fast_archive_state.json"
    state = dict(status="waiting_for_asrun", started_at=datetime.now().isoformat(), files=[])
    with state_path.open("x", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)

    def save():
        atomic_json(state_path, state)

    try:
        log("Queued FAST archive; waiting for ASRUN refresh to finish")
        deadline = time.monotonic() + 6 * 3600
        while True:
            dependency = json.loads((work / "asrun_state.json").read_text())
            if dependency["status"] == "complete":
                break
            if dependency["status"] == "failed":
                raise RuntimeError("ASRUN failed; archive queue stopped for review")
            if time.monotonic() > deadline:
                raise RuntimeError("ASRUN wait exceeded six hours; queue stopped for review")
            time.sleep(15)
        lake = work / "combined_lake"
        if not list(lake.glob("source=fast/year=*/month=*/day=*/part_*.parquet")):
            raise RuntimeError("No completed FAST lake files")
        state["status"] = "copying_and_verifying"
        save()
        publish(lake, archive, date(2026, 10, 11), state["files"], "fast", save)
        state["status"] = "validating"
        save()
        env = worker_environment(dict(os.environ, VG_ETL_BASE=str(ETL / "data")))
        for day in (9, 10, 11):
            with (work / f"validate_archive_fast_{day}.log").open("w", encoding="utf-8") as handle:
                subprocess.run([sys.executable, "-u", str(ETL / "src/tools/validate_daily_delivery.py"),
                    "--lake", str(archive), "--date", f"2026-10-{day:02}", "--sources", "fast",
                    "--mode", "structural", "--output-dir", str(work / "archive_validation")],
                    env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)
        state.update(status="complete", finished_at=datetime.now().isoformat())
        save()
        log("FAST archive through October 11 complete; local files retained")
    except BaseException as exc:
        state.update(status="failed", error=str(exc), finished_at=datetime.now().isoformat())
        save()
        raise


if __name__ == "__main__":
    main()
