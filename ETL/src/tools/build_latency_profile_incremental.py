#!/usr/bin/env python3
"""Incrementally build Veto latency profile tables from lake partitions."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd


ETL_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ETL_ROOT / "src"
DASHBOARD_DIR = SRC_ROOT / "dashboards" / "latencyDashboard"
PROFILE_ROOT = SRC_ROOT / "profile"
COMMON_ROOT = SRC_ROOT / "common"
for path in [ETL_ROOT, SRC_ROOT, DASHBOARD_DIR, PROFILE_ROOT, COMMON_ROOT]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import generate_latency as latency  # noqa: E402
from lake_partitions import (  # noqa: E402
    LakePartition,
    discover_partitions,
    resolve_lake_roots,
    split_path_list,
)
from vglive_core import DEFAULT_LAKE_FOLDER  # noqa: E402


TABLES = [
    "daily",
    "hourly",
    "channel_daily",
    "host_daily",
    "status_daily",
    "cache_daily",
    "geo_daily",
]
SUMMARY_METRICS = [
    "ttfb_p95_ms",
    "turnaround_p95_ms",
    "transfer_p95_ms",
    "throughput_p05",
]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def fmt_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default
    return payload if isinstance(payload, dict) else default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"tmp_{path.stem}_{int(time.time() * 1000)}{path.suffix}")
    tmp.unlink(missing_ok=True)
    df.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(path)


def day_path(lake: Path, source: str, day_value: date) -> Path:
    return (
        lake
        / f"source={source}"
        / f"year={day_value:%Y}"
        / f"month={day_value:%m}"
        / f"day={day_value:%d}"
    )


def discover_days(lake: Path, source: str, start: date | None, end: date | None) -> list[date]:
    root = lake / f"source={source}"
    days: list[date] = []
    for folder in root.glob("year=*/month=*/day=*"):
        if not folder.is_dir() or not any(folder.glob("part_*.parquet")):
            continue
        try:
            parts = {
                piece.split("=", 1)[0]: piece.split("=", 1)[1]
                for piece in folder.parts
                if "=" in piece
            }
            day_value = date(int(parts["year"]), int(parts["month"]), int(parts["day"]))
        except (KeyError, ValueError, IndexError):
            continue
        if start and day_value < start:
            continue
        if end and day_value > end:
            continue
        days.append(day_value)
    return sorted(set(days))


def signature_for_day(lake: Path, source: str, day_value: date) -> dict:
    files = sorted(day_path(lake, source, day_value).glob("part_*.parquet"))
    items = []
    total_bytes = 0
    max_mtime_ns = 0
    for file in files:
        stat = file.stat()
        total_bytes += int(stat.st_size)
        max_mtime_ns = max(max_mtime_ns, int(stat.st_mtime_ns))
        items.append(
            {
                "name": file.name,
                "bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    return {
        "file_count": len(files),
        "total_bytes": total_bytes,
        "max_mtime_ns": max_mtime_ns,
        "files": items,
    }


def signature_for_partition(partition: LakePartition) -> dict:
    items = []
    total_bytes = 0
    max_mtime_ns = 0
    for file in partition.files:
        stat = file.stat()
        total_bytes += int(stat.st_size)
        max_mtime_ns = max(max_mtime_ns, int(stat.st_mtime_ns))
        items.append(
            {
                "name": file.name,
                "bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    return {
        "file_count": len(items),
        "total_bytes": total_bytes,
        "max_mtime_ns": max_mtime_ns,
        "files": items,
    }


def comparable_signature(signature: dict | None) -> dict:
    """Return a signature that is stable when a lake day moves to archive."""
    signature = signature if isinstance(signature, dict) else {}
    files = []
    for item in signature.get("files", []):
        if not isinstance(item, dict):
            continue
        files.append(
            {
                "name": item.get("name"),
                "bytes": int(item.get("bytes") or 0),
                "mtime_ns": int(item.get("mtime_ns") or 0),
            }
        )
    files.sort(key=lambda item: (str(item["name"]), item["bytes"], item["mtime_ns"]))
    return {
        "file_count": int(signature.get("file_count") or len(files)),
        "total_bytes": int(signature.get("total_bytes") or 0),
        "max_mtime_ns": int(signature.get("max_mtime_ns") or 0),
        "files": files,
    }


def part_dir(parts_root: Path, source: str, day_value: date) -> Path:
    return parts_root / f"source={source}" / f"log_date={day_value.isoformat()}"


def part_ready(parts_root: Path, source: str, day_value: date) -> bool:
    folder = part_dir(parts_root, source, day_value)
    return all((folder / f"{name}.parquet").exists() for name in TABLES)


def start_heartbeat(
    stop_event: threading.Event,
    label: str,
    overall_index: int,
    total: int,
    started: float,
    interval: int,
) -> threading.Thread | None:
    if interval <= 0:
        return None

    def loop() -> None:
        while not stop_event.wait(interval):
            percent = (overall_index / total * 100) if total else 100.0
            log(
                f"[heartbeat] {overall_index}/{total} {percent:.1f}% {label} "
                f"still running, elapsed={fmt_seconds(time.time() - started)}"
            )

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def process_day(args: argparse.Namespace, partition: LakePartition, out_folder: Path) -> dict:
    day_value = date(partition.year, partition.month, partition.day)
    ns = argparse.Namespace(
        lake=args.lake,
        input_files=partition.files,
        start=day_value.isoformat(),
        end=day_value.isoformat(),
        window_days=0,
        source=partition.source,
        top_n=args.top_n,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_dir=args.temp_dir,
        dry_run=False,
        title="Veto Latency",
        out=args.html_out,
        profile_out=args.out_dir,
        from_profile=False,
    )
    tables = latency.build_tables(ns)
    for name, frame in tables.items():
        if name == "summary":
            continue
        if args.dry_run:
            log(f"[dry-run] would write {len(frame):,} rows -> {out_folder / f'{name}.parquet'}")
        else:
            atomic_write_parquet(frame, out_folder / f"{name}.parquet")
    return {
        "rows": {name: int(len(frame)) for name, frame in tables.items()},
        "base_rows": int(tables.get("summary", pd.DataFrame()).get("rows", pd.Series([0])).iloc[0])
        if not tables.get("summary", pd.DataFrame()).empty
        else 0,
    }


def read_part_table(parts_root: Path, name: str) -> pd.DataFrame:
    frames = []
    for file in sorted(parts_root.glob(f"source=*/log_date=*/{name}.parquet")):
        frames.append(pd.read_parquet(file))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def weighted_average(df: pd.DataFrame, column: str, weight_col: str = "rows") -> float:
    if column not in df or weight_col not in df or df.empty:
        return 0.0
    values = pd.to_numeric(df[column], errors="coerce")
    weights = pd.to_numeric(df[weight_col], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return 0.0
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def build_summary(merged: dict[str, pd.DataFrame]) -> pd.DataFrame:
    daily = merged.get("daily", pd.DataFrame())
    channel = merged.get("channel_daily", pd.DataFrame())
    host = merged.get("host_daily", pd.DataFrame())
    if daily.empty:
        return pd.DataFrame([{}])
    ts = daily[daily["extension"].astype(str).str.lower() == "ts"] if "extension" in daily else daily.iloc[0:0]
    playlists = daily[daily["extension"].astype(str).str.lower() == "m3u8"] if "extension" in daily else daily.iloc[0:0]
    row = {
        "first_date": str(daily["log_date"].min()) if "log_date" in daily else "",
        "last_date": str(daily["log_date"].max()) if "log_date" in daily else "",
        "rows": int(pd.to_numeric(daily.get("rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "ts_rows": int(pd.to_numeric(ts.get("rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "playlist_rows": int(pd.to_numeric(playlists.get("rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "sources": int(daily["source"].nunique()) if "source" in daily else 0,
        "channels": int(channel["channel_name"].nunique()) if "channel_name" in channel else 0,
        "hosts": int(host["reqHost"].nunique()) if "reqHost" in host else 0,
        "ttfb_rows": int(pd.to_numeric(daily.get("ttfb_rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
    }
    for metric in SUMMARY_METRICS:
        row[metric] = weighted_average(daily, metric)
    return pd.DataFrame([row])


def merge_profile(parts_root: Path, out_dir: Path, dry_run: bool) -> dict:
    merged: dict[str, pd.DataFrame] = {}
    for table in TABLES:
        frame = read_part_table(parts_root, table)
        merged[table] = frame
        if dry_run:
            log(f"[dry-run] would merge {table}: {len(frame):,} rows")
        else:
            atomic_write_parquet(frame, out_dir / f"{table}.parquet")
            log(f"[merge] {table}: {len(frame):,} rows")

    summary = build_summary(merged)
    merged["summary"] = summary
    if not dry_run:
        atomic_write_parquet(summary, out_dir / "summary.parquet")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parts_root": str(parts_root),
        "tables": {name: int(len(frame)) for name, frame in merged.items()},
        "sources": sorted(
            set(
                merged["daily"]["source"].dropna().astype(str).tolist()
                if not merged.get("daily", pd.DataFrame()).empty and "source" in merged["daily"]
                else []
            )
        ),
    }
    if not dry_run:
        write_json(out_dir / "latency_manifest.json", manifest)
    return manifest


def render_html(args: argparse.Namespace) -> None:
    cmd_args = argparse.Namespace(
        lake=args.lake,
        out=args.html_out,
        profile_out=args.out_dir,
        title=args.title,
        start=None,
        end=None,
        window_days=0,
        source="all",
        from_profile=True,
        top_n=args.top_n,
        threads=args.threads,
        memory_limit=args.memory_limit,
        temp_dir=args.temp_dir,
        dry_run=args.dry_run,
    )
    tables = latency.load_tables_from_profile(args.out_dir)
    payload = latency.build_payload(tables, cmd_args)
    chartjs = latency.load_chartjs(latency.CHARTJS_CACHE, fallback="window.Chart=null;")
    html = latency.render_template(
        latency.HERE / "template.html",
        DATA_BLOB=latency.json_blob(payload),
        CHARTJS=chartjs or "window.Chart=null;",
    )
    if args.dry_run:
        log(f"[dry-run] would render HTML chars={len(html):,} -> {args.html_out}")
        return
    args.html_out.parent.mkdir(parents=True, exist_ok=True)
    args.html_out.write_text(html, encoding="utf-8")
    log(f"[html] wrote {args.html_out} ({args.html_out.stat().st_size / 1024:.1f} KB)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally build latency profile tables.")
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE_FOLDER)
    parser.add_argument(
        "--archive-lake",
        action="append",
        default=[],
        help="Optional archive lake root(s). Can be repeated or comma/semicolon separated.",
    )
    parser.add_argument("--source", choices=["fast", "stream"], default="fast")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--out-dir", type=Path, default=ETL_ROOT / "output" / "latency" / "profile")
    parser.add_argument("--parts-dir", type=Path, default=ETL_ROOT / "output" / "latency" / "parts")
    parser.add_argument("--state", type=Path, default=ETL_ROOT / "output" / "latency" / "latency_incremental_state.json")
    parser.add_argument("--html-out", type=Path, default=ETL_ROOT / "output" / "latency" / "veto_latency.html")
    parser.add_argument("--title", default="Veto Latency")
    parser.add_argument("--top-n", type=int, default=300)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--memory-limit", default="16GB")
    parser.add_argument("--temp-dir", type=Path, default=ETL_ROOT / "output" / "cache" / "duckdb_temp")
    parser.add_argument("--max-days", type=int, default=0, help="Process at most N changed days this run. 0 means all.")
    parser.add_argument("--heartbeat-seconds", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.lake = args.lake.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    args.parts_dir = args.parts_dir.expanduser().resolve()
    args.state = args.state.expanduser().resolve()
    args.html_out = args.html_out.expanduser().resolve()
    args.temp_dir = args.temp_dir.expanduser().resolve()

    start = parse_date(args.start)
    end = parse_date(args.end)
    if start and end and start > end:
        raise SystemExit("--start cannot be after --end.")
    if not args.lake.exists():
        raise SystemExit(f"Lake folder not found: {args.lake}")

    requested_archives: list[Path] = []
    for value in args.archive_lake:
        requested_archives.extend(split_path_list(value))
    lake_roots = resolve_lake_roots(args.lake, requested_archives or None)
    partitions = discover_partitions(
        lake_roots,
        source=args.source,
        start=start,
        end=end,
    )
    if args.max_days and args.max_days > 0:
        partitions = partitions[: args.max_days]
    if not partitions:
        raise SystemExit(f"No lake days found for source={args.source}.")

    state = read_json(args.state, {"version": 1, "days": {}})
    state.setdefault("days", {})

    log(
        f"Latency incremental start: source={args.source}, days={len(partitions)}, "
        f"range={partitions[0].date_text} -> {partitions[-1].date_text}, force={args.force}"
    )
    started_all = time.time()
    processed = 0
    skipped = 0
    failed = 0

    for index, partition in enumerate(partitions, start=1):
        day_value = date(partition.year, partition.month, partition.day)
        percent = index / len(partitions) * 100
        key = f"{partition.source}|{partition.date_text}"
        signature = signature_for_partition(partition)
        previous = state["days"].get(key, {})
        up_to_date = (
            not args.force
            and comparable_signature(previous.get("signature")) == comparable_signature(signature)
            and previous.get("status") == "done"
            and part_ready(args.parts_dir, args.source, day_value)
        )
        if up_to_date:
            skipped += 1
            log(
                f"[skip] {index}/{len(partitions)} {percent:.1f}% source={args.source} "
                f"date={day_value} files={signature['file_count']} bytes={signature['total_bytes']:,}"
            )
            continue

        label = f"source={args.source} date={day_value}"
        log(
            f"[progress] {index}/{len(partitions)} {percent:.1f}% processing {label} "
            f"files={signature['file_count']} bytes={signature['total_bytes']:,}"
        )
        stop_event = threading.Event()
        heartbeat = start_heartbeat(
            stop_event,
            label,
            index,
            len(partitions),
            time.time(),
            args.heartbeat_seconds,
        )
        day_started = time.time()
        try:
            result = process_day(args, partition, part_dir(args.parts_dir, partition.source, day_value))
            duration = time.time() - day_started
            processed += 1
            state["days"][key] = {
                "source": args.source,
                "date": day_value.isoformat(),
                "signature": signature,
                "status": "done",
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "duration_seconds": round(duration, 3),
                "result": result,
            }
            if not args.dry_run:
                write_json(args.state, state)
            avg = (time.time() - started_all) / index
            eta = avg * (len(partitions) - index)
            log(
                f"[done] {index}/{len(partitions)} {percent:.1f}% {label} "
                f"rows={result.get('base_rows', 0):,} duration={fmt_seconds(duration)} "
                f"overall_elapsed={fmt_seconds(time.time() - started_all)} eta={fmt_seconds(eta)}"
            )
        except Exception as exc:
            failed += 1
            state["days"][key] = {
                "source": args.source,
                "date": day_value.isoformat(),
                "signature": signature,
                "status": "failed",
                "failed_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
            }
            if not args.dry_run:
                write_json(args.state, state)
            log(f"[failed] {index}/{len(partitions)} {percent:.1f}% {label}: {exc}")
            raise
        finally:
            stop_event.set()
            if heartbeat is not None:
                heartbeat.join(timeout=2)

    log(f"Merging latency profile from parts: {args.parts_dir}")
    manifest = merge_profile(args.parts_dir, args.out_dir, args.dry_run)
    if not args.no_render:
        render_html(args)

    log(
        "Latency incremental complete: "
        f"processed={processed}, skipped={skipped}, failed={failed}, "
        f"elapsed={fmt_seconds(time.time() - started_all)}, tables={manifest.get('tables', {})}"
    )


if __name__ == "__main__":
    main()
