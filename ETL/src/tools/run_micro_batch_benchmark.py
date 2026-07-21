"""Run an isolated, full-pipeline micro-batch benchmark from timestamped raw logs.

This tool does not touch the production lake or dashboard output. It selects raw
``.gz`` files by the Unix timestamp embedded in their filename, creates hard-link
staging inputs (so no second copy of the raw logs is stored), and invokes the
normal orchestrator against an isolated base/output pair.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as datetime_time
from pathlib import Path
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
FILENAME_EPOCH = re.compile(r"-(?P<epoch>\d{10})-\d+-ds\.gz$", re.IGNORECASE)
SOURCE_FOLDERS = {
    "fast": "Veto fast Backup",
    "stream": "Veto Stream Backup",
}


@dataclass(frozen=True)
class SelectedFile:
    """A raw object selected for an IST micro-batch window."""

    source: str
    path: str
    epoch_seconds: int
    timestamp_ist: str
    bytes: int


def parse_clock(value: str) -> datetime_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must use 24-hour HH:MM format") from exc


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def filename_epoch(path: Path) -> int | None:
    match = FILENAME_EPOCH.search(path.name)
    return int(match.group("epoch")) if match else None


def select_files(
    raw_root: Path,
    source: str,
    target_date: date,
    start_clock: datetime_time,
    end_clock: datetime_time,
) -> list[SelectedFile]:
    """Select files whose authoritative filename epoch falls within the IST window."""
    source_root = raw_root / SOURCE_FOLDERS[source] / target_date.strftime("%m") / target_date.strftime("%d")
    if not source_root.is_dir():
        raise FileNotFoundError(f"Raw {source} folder does not exist: {source_root}")

    start = datetime.combine(target_date, start_clock, IST)
    end = datetime.combine(target_date, end_clock, IST)
    if end <= start:
        raise ValueError("--end must be later than --start on the selected date")

    selected: list[SelectedFile] = []
    for path in source_root.rglob("*.gz"):
        epoch = filename_epoch(path)
        if epoch is None:
            continue
        timestamp = datetime.fromtimestamp(epoch, tz=IST)
        if start <= timestamp < end:
            selected.append(
                SelectedFile(
                    source=source,
                    path=str(path),
                    epoch_seconds=epoch,
                    timestamp_ist=timestamp.isoformat(),
                    bytes=path.stat().st_size,
                )
            )
    return sorted(selected, key=lambda item: (item.epoch_seconds, item.path))


def hard_link_selected_files(
    selected: list[SelectedFile],
    raw_root: Path,
    stage_raw_root: Path,
) -> None:
    """Stage via hard links so benchmark inputs cannot consume a second raw copy."""
    for item in selected:
        source_path = Path(item.path)
        relative = source_path.relative_to(raw_root)
        destination = stage_raw_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.stat().st_size != source_path.stat().st_size:
                raise RuntimeError(f"Existing staged file size differs: {destination}")
            continue
        try:
            os.link(source_path, destination)
        except OSError as exc:
            # A hard link is intentional: silently copying hundreds of thousands of
            # source files would invalidate disk and I/O measurements.
            raise RuntimeError(
                f"Could not hard-link {source_path} into benchmark staging. "
                "Both locations must be on the same NTFS volume."
            ) from exc


def write_manifest(
    run_root: Path,
    selected: list[SelectedFile],
    target_date: date,
    start_clock: datetime_time,
    end_clock: datetime_time,
) -> Path:
    manifest_path = run_root / "selection_manifest.json"
    payload = {
        "schema_version": 1,
        "created_at_ist": datetime.now(IST).isoformat(),
        "target_date_ist": target_date.isoformat(),
        "window_ist": {
            "start": start_clock.strftime("%H:%M"),
            "end_exclusive": end_clock.strftime("%H:%M"),
        },
        "file_count": len(selected),
        "total_bytes": sum(item.bytes for item in selected),
        "files": [asdict(item) for item in selected],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def build_pipeline_command(
    etl_root: Path,
    run_root: Path,
    target_date: date,
    sources: str,
    workers: int,
) -> list[str]:
    workspace_root = etl_root.parent
    python = workspace_root / "venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise FileNotFoundError(f"Virtual-environment Python not found: {python}")

    base = run_root / "data"
    output_root = run_root / "output"
    raw_root = run_root / "raw" / "Veto Logs Backup"
    temp_dir = run_root / "temp"
    return [
        str(python),
        str(etl_root / "src" / "orchestrator" / "run_pipeline.py"),
        "--base", str(base),
        "--output-root", str(output_root),
        "--overview-lake-root", str(base / "lake"),
        "--overview-sources", "fast,stream",
        "--etl1-daily-date", target_date.isoformat(),
        "--etl1-daily-raw-root", str(raw_root),
        "--etl1-stream-name", SOURCE_FOLDERS["stream"],
        "--etl1-fast-name", SOURCE_FOLDERS["fast"],
        "--etl1-sources", sources,
        "--etl1-workers", str(workers),
        "--etl1-compression", "zstd",
        "--lake-repair-lookback-days", "0",
        "--deep-profile-mode", "full",
        "--deep-profile-threads", "4",
        "--deep-profile-memory", "16GB",
        "--deep-profile-temp-dir", str(temp_dir),
        "--deep-profile-max-temp-size", "30GB",
        "--deep-profile-output-format", "parquet",
        "--deep-profile-querystr-profile", "skip",
        "--deep-profile-top-values", "skip",
        "--deep-profile-column-fill", "reuse",
        "--run-ua-profile",
        # Network API work is deliberately excluded from the latency benchmark. It
        # is independent enrichment and must remain asynchronous in a micro-batch.
        "--ua-api-limit", "0",
        "--concurrency-window-days", "1",
        "--latency-window-days", "1",
        "--state-name", "micro_benchmark",
        "--continue-on-error",
    ]


def main() -> None:
    etl_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, required=True, help="IST date: YYYY-MM-DD")
    parser.add_argument("--start", type=parse_clock, required=True, help="IST window start: HH:MM")
    parser.add_argument("--end", type=parse_clock, required=True, help="IST exclusive window end: HH:MM")
    parser.add_argument("--source", choices=["both", "fast", "stream"], default="both")
    parser.add_argument("--workers", type=int, default=2, help="001.py worker processes")
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="Isolated benchmark folder. Defaults below output/benchmarks/.",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help="Raw root containing source folders. Defaults to the production raw root.",
    )
    parser.add_argument("--prepare-only", action="store_true", help="Stage and manifest files without running ETL.")
    args = parser.parse_args()

    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")

    raw_root = (
        args.raw_root.expanduser().resolve()
        if args.raw_root
        else etl_root / "data" / "raw" / "Veto Logs Backup"
    )
    if not raw_root.is_dir():
        raise SystemExit(f"Production raw root not found: {raw_root}")

    run_name = (
        f"micro_{args.date.strftime('%Y%m%d')}_"
        f"{args.start.strftime('%H%M')}_{args.end.strftime('%H%M')}_{args.source}"
    )
    run_root = args.run_root.resolve() if args.run_root else etl_root / "output" / "benchmarks" / run_name
    stage_raw_root = run_root / "raw" / "Veto Logs Backup"
    sources = ["fast", "stream"] if args.source == "both" else [args.source]

    selected = [
        item
        for source in sources
        for item in select_files(raw_root, source, args.date, args.start, args.end)
    ]
    if not selected:
        raise SystemExit("No timestamped .gz files matched the requested IST window.")

    manifest = write_manifest(run_root, selected, args.date, args.start, args.end)
    print(f"Selected {len(selected):,} files ({sum(item.bytes for item in selected) / 1_000_000:.1f} MB).")
    print(f"Manifest: {manifest}")
    hard_link_selected_files(selected, raw_root, stage_raw_root)
    print(f"Hard-link staging ready: {stage_raw_root}")
    if args.prepare_only:
        return

    command = build_pipeline_command(etl_root, run_root, args.date, args.source, args.workers)
    run_log = run_root / "pipeline.out.log"
    # The orchestrator validates --base before 001.py creates any stage artifacts.
    # Create the isolated base up front so this trial never falls back to production.
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    print("Starting isolated full-pipeline micro-batch benchmark.")
    print(f"Log: {run_log}")
    started = time.perf_counter()
    with run_log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(command, cwd=etl_root, stdout=handle, stderr=subprocess.STDOUT, text=True)
    elapsed_seconds = time.perf_counter() - started
    summary = {
        "finished_at_ist": datetime.now(IST).isoformat(),
        "exit_code": result.returncode,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "elapsed_minutes": round(elapsed_seconds / 60, 2),
        "command": command,
        "pipeline_log": str(run_log),
    }
    (run_root / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
