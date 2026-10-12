"""Targeted October 9-11 ASRUN catch-up, retaining the paused full recovery."""

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

from priority_stream_lake import (
    ETL, atomic_json, build_day, log, pq, sha256, worker_environment,
)


START, END = "2026-10-09", "2026-10-11"


def link_lake(source, destination):
    """Make an immutable input union without copying multi-GB lake files."""
    for part in sorted(source.glob("source=fast/year=*/month=*/day=*/part_*.parquet")):
        relative = part.relative_to(source)
        values = dict(p.split("=", 1) for p in relative.parts[:-1])
        day = date(int(values["year"]), int(values["month"]), int(values["day"]))
        if not START <= day.isoformat() <= END:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not os.path.samefile(part, target) and sha256(part) != sha256(target):
                raise RuntimeError(f"Conflicting FAST partition: {relative}")
        else:
            os.link(part, target)


def validate_identity(baseline, refreshed):
    import duckdb

    with duckdb.connect() as con:
        con.execute("SET threads=4")
        before = con.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE log_date < ?",
            [str(baseline), START],
        ).fetchone()[0]
        after = con.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE log_date < ?",
            [str(refreshed), START],
        ).fetchone()[0]
        if before != after:
            raise RuntimeError("Identity rebuild lost historical rows; refusing refresh")
        rows = con.execute(
            "SELECT source,log_date,min(minute_ist),max(minute_ist),count(*) "
            "FROM read_parquet(?) WHERE log_date BETWEEN ? AND ? GROUP BY 1,2",
            [str(refreshed), START, END],
        ).fetchall()
    expected = {(source, f"2026-10-{day:02}") for source in ("fast", "stream") for day in (9, 10, 11)}
    if {(r[0], str(r[1])[:10]) for r in rows} != expected:
        raise RuntimeError("Missing FAST/STREAM identity date(s); refusing refresh")
    for source, day, first, last, count in rows:
        if str(first)[11:16] != "00:00" or str(last)[11:16] != "23:59":
            raise RuntimeError(f"Partial identity coverage: {source} {day}: {first} - {last}")
    return [dict(source=s, date=str(d), first=str(f), last=str(t), rows=n) for s, d, f, t, n in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--stream-work", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    if not work.is_relative_to((ETL / "output").resolve()):
        raise SystemExit("Work must be inside ETL/output")
    stream_state = json.loads((args.stream_work / "priority_state.json").read_text())
    hold = json.loads((args.stream_work / "manual_recovery_hold.json").read_text())
    if stream_state.get("status") != "complete" or hold.get("status") != "held_until_user_resume":
        raise SystemExit("Requires completed STREAM lake and explicit full-recovery hold")
    work.mkdir(parents=True, exist_ok=True)
    state_path = work / "asrun_state.json"
    state = dict(status="starting", started_at=datetime.now().isoformat(), through=END, recovery="held")
    with state_path.open("x", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    env = worker_environment(dict(os.environ, VG_ETL_BASE=str(ETL / "data"), PYTHONUNBUFFERED="1"))

    def phase(name):
        state.update(status=name, updated_at=datetime.now().isoformat())
        atomic_json(state_path, state)
        log(name)

    def run(name, command):
        phase(name)
        with (work / f"{name}.log").open("w", encoding="utf-8") as handle:
            subprocess.run([sys.executable, "-u", *map(str, command)], cwd=ETL,
                           env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)

    try:
        if shutil.disk_usage(work).free < 60 * 1024**3:
            raise RuntimeError("Need 60 GiB free for non-destructive FAST catch-up")
        raw_root = args.archive / "source=AsRUN"
        inputs = []
        for path in sorted(raw_root.glob("ASRUN-*.txt")):
            try:
                day = datetime.strptime(path.stem[6:], "%d%m%y").date().isoformat()
            except ValueError:
                continue
            if day <= END:
                inputs.append(path)
        if not any(p.name.upper() == "ASRUN-111026.TXT" for p in inputs):
            raise RuntimeError("October 11 ASRUN source file is missing")
        phase("building_fast_10_11")
        lake = work / "combined_lake"
        link_lake(ETL / "data" / "lake", lake)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(build_day, date(2026, 10, d), work, "fast") for d in (10, 11)]
            for future in as_completed(futures):
                link_lake(future.result(), lake)
        for day in (9, 10, 11):
            run(f"validate_fast_{day}", [ETL / "src/tools/validate_daily_delivery.py",
                "--lake", lake, "--date", f"2026-10-{day:02}", "--sources", "fast",
                "--mode", "structural", "--output-dir", work / "validation"])
        baseline = ETL / "output/watch_hours/concurrency/identity_minute.parquet"
        audience = work / "audience"
        audience.mkdir()
        shutil.copy2(baseline, audience / "identity_minute.parquet")
        for source, source_lake in (("fast", lake), ("stream", args.archive)):
            run(f"identity_{source}", [ETL / "src/tools/build_identity_minute.py",
                "--source", source, "--lake", source_lake, "--archive-lake", source_lake,
                "--start", START, "--end", END, "--out-dir", audience,
                "--threads", "10", "--memory-limit", "12GB", "--temp-dir", work / "identity_scratch"])
        state["audience_coverage"] = validate_identity(baseline, audience / "identity_minute.parquet")
        phase("preparing_asrun_refresh")
        demo = ETL / "asrun_demo"
        parsed, output = work / "parsed", work / "dashboard"
        shutil.copytree(demo / "data/parsed", parsed)
        for kind in ("YOUTUBE", "AMAGI", "FCT", "NCT"):
            env[f"VG_ASRUN_{kind}_ROOT"] = str(args.archive / ("source=" + {"YOUTUBE": "Youtube", "AMAGI": "amagi"}.get(kind, kind)))
        run("asrun_refresh", [demo / "src/build_asrun_demo.py", "--channel",
            "Unassigned - stakeholder mapping required", "--identity-minute", audience / "identity_minute.parquet",
            "--parsed-dir", parsed, "--output-dir", output, "--verbose", "--input", *inputs])
        if not (output / "data/viewer/viewer_2026-10-11.js").is_file():
            raise RuntimeError("ASRUN October 11 audience sidecar missing")
        if not (output / "asrun_delivery_demo.html").is_file():
            raise RuntimeError("ASRUN dashboard HTML missing")
        phase("publishing_asrun_with_backup")
        # Preserve every previous generated artifact before replacing any live file.
        shutil.copytree(demo / "output", work / "previous_dashboard")
        files = sorted(p for p in output.rglob("*") if p.is_file())
        files.sort(key=lambda p: (p.suffix == ".html", p.name == "asrun_delivery_data.js"))
        for source in files:
            target = demo / "output" / source.relative_to(output)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".priority-new")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        state.update(dashboard=str(demo / "output/asrun_delivery_demo.html"),
                     identity_mart=str(audience / "identity_minute.parquet"),
                     finished_at=datetime.now().isoformat())
        phase("complete")
    except BaseException as exc:
        state.update(status="failed", error=str(exc), finished_at=datetime.now().isoformat())
        atomic_json(state_path, state)
        log(f"FAILED: {exc}; existing inputs retained; full recovery remains held")
        raise


if __name__ == "__main__":
    main()
