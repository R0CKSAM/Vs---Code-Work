#!/usr/bin/env python3
"""Validate one completed FAST/STREAM day before dashboards are published.

This is the data half of the ETL acceptance gate. The orchestrator already
records process exit codes; this tool verifies that the successful process
actually produced a complete, non-overlapping source day and that the merged
daily profile reconciles to the selected lake partition.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq


IST = ZoneInfo("Asia/Kolkata")
SCHEMA_VERSION = 1
DEFAULT_ARCHIVE = Path(r"Z:\Veto Logs Backup\DO NOT DELETE")
ARCHIVE_ENV_NAMES = (
    "VG_ETL_ARCHIVE_LAKE_ROOTS",
    "VG_ETL_ARCHIVE_LAKE_ROOT",
    "VG_ARCHIVE_LAKE_ROOTS",
    "VG_ARCHIVE_LAKE_ROOT",
)


@dataclass(frozen=True)
class FileEvidence:
    path: str
    rows: int
    start_ist: str
    end_ist: str
    start_epoch: float | None
    end_epoch: float | None


@dataclass(frozen=True)
class PartitionEvidence:
    source: str
    date: str
    root: str
    day_dir: str
    priority: int
    files: list[FileEvidence]
    rows: int
    start_ist: str
    end_ist: str
    start_epoch: float | None
    end_epoch: float | None
    coverage_seconds: float
    start_gap_minutes: float | None
    end_gap_minutes: float | None
    max_internal_gap_minutes: float
    overlap_minutes: float
    full_day: bool


def split_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(part.strip().strip('"')) for part in re.split(r"[;,]", value) if part.strip()]


def archive_roots(cli_values: Iterable[str]) -> list[Path]:
    roots: list[Path] = []
    for value in cli_values:
        roots.extend(split_paths(value))
    for name in ARCHIVE_ENV_NAMES:
        roots.extend(split_paths(os.getenv(name)))
    try:
        if DEFAULT_ARCHIVE.exists():
            roots.append(DEFAULT_ARCHIVE)
    except OSError:
        # The archive is optional. A disconnected or permission-restricted
        # mount must not block validation of the primary lake.
        pass
    return roots


def unique_roots(primary: Path, archives: Iterable[Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in [primary, *archives]:
        try:
            root = raw.expanduser().resolve()
        except OSError:
            continue
        key = str(root).casefold()
        if key in seen or not root.exists():
            continue
        seen.add(key)
        roots.append(root)
    return roots


def parse_stat(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_epoch(value: float | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, tz=IST).isoformat(timespec="seconds")


def parquet_evidence(path: Path) -> FileEvidence:
    metadata = pq.read_metadata(path)
    mins: list[float] = []
    maxs: list[float] = []
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            if column.path_in_schema != "reqTimeSec" or column.statistics is None:
                continue
            minimum = parse_stat(column.statistics.min)
            maximum = parse_stat(column.statistics.max)
            if minimum is not None:
                mins.append(minimum)
            if maximum is not None:
                maxs.append(maximum)
    start = min(mins) if mins else None
    end = max(maxs) if maxs else None
    return FileEvidence(
        path=str(path),
        rows=int(metadata.num_rows),
        start_ist=format_epoch(start),
        end_ist=format_epoch(end),
        start_epoch=start,
        end_epoch=end,
    )


def merge_intervals(files: Iterable[FileEvidence]) -> tuple[float, float, float]:
    intervals = sorted(
        (item.start_epoch, item.end_epoch)
        for item in files
        if item.start_epoch is not None and item.end_epoch is not None
    )
    if not intervals:
        return 0.0, 0.0, 0.0
    merged: list[list[float]] = []
    overlap_seconds = 0.0
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue
        overlap_seconds += max(0.0, min(end, merged[-1][1]) - start)
        merged[-1][1] = max(merged[-1][1], end)
    coverage_seconds = sum(end - start for start, end in merged)
    gaps = [merged[index + 1][0] - merged[index][1] for index in range(len(merged) - 1)]
    return coverage_seconds, max(gaps, default=0.0), overlap_seconds


def build_partition(
    root: Path,
    priority: int,
    source: str,
    target: date,
    start_tolerance_minutes: int,
    end_tolerance_minutes: int,
) -> PartitionEvidence | None:
    day_dir = (
        root
        / f"source={source}"
        / f"year={target.year:04d}"
        / f"month={target.month:02d}"
        / f"day={target.day:02d}"
    )
    files = sorted(day_dir.glob("part_*.parquet")) if day_dir.is_dir() else []
    if not files:
        return None
    evidence: list[FileEvidence] = []
    for path in files:
        try:
            evidence.append(parquet_evidence(path))
        except (OSError, ValueError, TypeError):
            evidence.append(FileEvidence(str(path), 0, "", "", None, None))

    starts = [item.start_epoch for item in evidence if item.start_epoch is not None]
    ends = [item.end_epoch for item in evidence if item.end_epoch is not None]
    start_epoch = min(starts) if starts else None
    end_epoch = max(ends) if ends else None
    day_start = datetime.combine(target, time.min, tzinfo=IST).timestamp()
    day_end = datetime.combine(target, time.max, tzinfo=IST).timestamp()
    coverage_seconds, max_gap_seconds, overlap_seconds = merge_intervals(evidence)
    start_gap = ((start_epoch - day_start) / 60) if start_epoch is not None else None
    end_gap = ((day_end - end_epoch) / 60) if end_epoch is not None else None
    full_day = bool(
        start_epoch is not None
        and end_epoch is not None
        and start_gap <= start_tolerance_minutes
        and end_gap <= end_tolerance_minutes
        and max_gap_seconds <= max(start_tolerance_minutes, end_tolerance_minutes) * 60
    )
    return PartitionEvidence(
        source=source,
        date=target.isoformat(),
        root=str(root),
        day_dir=str(day_dir),
        priority=priority,
        files=evidence,
        rows=sum(item.rows for item in evidence),
        start_ist=format_epoch(start_epoch),
        end_ist=format_epoch(end_epoch),
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        coverage_seconds=round(coverage_seconds, 3),
        start_gap_minutes=round(start_gap, 3) if start_gap is not None else None,
        end_gap_minutes=round(end_gap, 3) if end_gap is not None else None,
        max_internal_gap_minutes=round(max_gap_seconds / 60, 3),
        overlap_minutes=round(overlap_seconds / 60, 3),
        full_day=full_day,
    )


def partition_score(item: PartitionEvidence) -> tuple[int, float, int, int]:
    return (int(item.full_day), item.coverage_seconds, item.rows, -item.priority)


def choose_partition(
    candidates: list[PartitionEvidence],
    start_tolerance_minutes: int,
    end_tolerance_minutes: int,
) -> PartitionEvidence | None:
    if not candidates:
        return None

    winners: dict[str, tuple[FileEvidence, PartitionEvidence]] = {}
    for candidate in candidates:
        for item in candidate.files:
            key = Path(item.path).name.casefold()
            existing = winners.get(key)
            coverage = (item.end_epoch or 0.0) - (item.start_epoch or 0.0)
            score = (coverage, item.rows, -candidate.priority)
            if existing is not None:
                old_item, old_candidate = existing
                old_coverage = (old_item.end_epoch or 0.0) - (old_item.start_epoch or 0.0)
                if score <= (old_coverage, old_item.rows, -old_candidate.priority):
                    continue
            winners[key] = (item, candidate)

    selected_files = [item[0] for item in winners.values()]
    starts = [item.start_epoch for item in selected_files if item.start_epoch is not None]
    ends = [item.end_epoch for item in selected_files if item.end_epoch is not None]
    start_epoch = min(starts) if starts else None
    end_epoch = max(ends) if ends else None
    target = date.fromisoformat(candidates[0].date)
    day_start = datetime.combine(target, time.min, tzinfo=IST).timestamp()
    day_end = datetime.combine(target, time.max, tzinfo=IST).timestamp()
    coverage_seconds, max_gap_seconds, overlap_seconds = merge_intervals(selected_files)
    start_gap = ((start_epoch - day_start) / 60) if start_epoch is not None else None
    end_gap = ((day_end - end_epoch) / 60) if end_epoch is not None else None
    full_day = bool(
        start_epoch is not None
        and end_epoch is not None
        and start_gap <= start_tolerance_minutes
        and end_gap <= end_tolerance_minutes
        and max_gap_seconds <= max(start_tolerance_minutes, end_tolerance_minutes) * 60
    )
    roots = list(dict.fromkeys(item[1].root for item in winners.values()))
    day_dirs = list(dict.fromkeys(item[1].day_dir for item in winners.values()))
    return PartitionEvidence(
        source=candidates[0].source,
        date=candidates[0].date,
        root="; ".join(roots),
        day_dir="; ".join(day_dirs),
        priority=min(item[1].priority for item in winners.values()),
        files=sorted(selected_files, key=lambda item: (Path(item.path).name.casefold(), item.path)),
        rows=sum(item.rows for item in selected_files),
        start_ist=format_epoch(start_epoch),
        end_ist=format_epoch(end_epoch),
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        coverage_seconds=round(coverage_seconds, 3),
        start_gap_minutes=round(start_gap, 3) if start_gap is not None else None,
        end_gap_minutes=round(end_gap, 3) if end_gap is not None else None,
        max_internal_gap_minutes=round(max_gap_seconds / 60, 3),
        overlap_minutes=round(overlap_seconds / 60, 3),
        full_day=full_day,
    )


def source_result(
    roots: list[Path],
    source: str,
    target: date,
    start_tolerance_minutes: int,
    end_tolerance_minutes: int,
    max_overlap_minutes: int,
) -> dict[str, Any]:
    candidates = [
        item
        for priority, root in enumerate(roots)
        if (
            item := build_partition(
                root,
                priority,
                source,
                target,
                start_tolerance_minutes,
                end_tolerance_minutes,
            )
        )
        is not None
    ]
    selected = choose_partition(candidates, start_tolerance_minutes, end_tolerance_minutes)
    if selected is None:
        return {
            "source": source,
            "status": "MISSING",
            "hard_failure": True,
            "message": f"No {source.upper()} lake partition exists for {target.isoformat()}.",
            "selected": None,
            "candidates": [],
        }

    status = "PASS"
    reasons: list[str] = []
    if not selected.full_day:
        status = "PARTIAL"
        reasons.append(
            f"coverage {selected.start_ist or 'unknown'} to {selected.end_ist or 'unknown'}"
        )
    unreadable = [item.path for item in selected.files if item.start_epoch is None or item.rows <= 0]
    if unreadable:
        status = "FAILED"
        reasons.append(f"{len(unreadable)} unreadable or unbounded parquet file(s)")
    message = "; ".join(reasons) if reasons else "Full-day source coverage passed."
    return {
        "source": source,
        "status": status,
        "hard_failure": status in {"MISSING", "PARTIAL", "DUPLICATE", "FAILED"},
        "message": message,
        "selected": asdict(selected),
        "candidates": [asdict(item) for item in candidates],
    }


def load_daily_volume(profile_dir: Path) -> pd.DataFrame:
    candidates = [
        profile_dir.parent / "daily_tables" / "daily_volume.parquet",
        profile_dir / "daily_volume.parquet",
    ]
    for path in candidates:
        if path.is_file():
            return pd.read_parquet(path)
    return pd.DataFrame()


def load_channel_daily(profile_dir: Path) -> pd.DataFrame:
    path = profile_dir.parent / "daily_tables" / "channel_audience_daily.parquet"
    return pd.read_parquet(path) if path.is_file() else pd.DataFrame()


def reconcile_profile(
    source_results: list[dict[str, Any]],
    profile_dir: Path,
    target: date,
    tolerance_pct: float,
    tolerance_rows: int,
) -> list[dict[str, Any]]:
    daily = load_daily_volume(profile_dir)
    results: list[dict[str, Any]] = []
    if daily.empty or not {"log_date", "source", "rows"}.issubset(daily.columns):
        return [{
            "status": "REVIEW",
            "message": "Daily volume mart is unavailable; profile-to-lake reconciliation was not run.",
        }]
    daily = daily.copy()
    daily["log_date"] = daily["log_date"].astype(str)
    daily["source"] = daily["source"].astype(str).str.lower()
    for source_item in source_results:
        source = source_item["source"]
        selected = source_item.get("selected")
        matched = daily[(daily["log_date"] == target.isoformat()) & (daily["source"] == source)]
        profile_rows = int(pd.to_numeric(matched["rows"], errors="coerce").fillna(0).sum())
        lake_rows = int(selected["rows"]) if selected else 0
        delta = profile_rows - lake_rows
        allowed_delta = max(tolerance_rows, int(lake_rows * tolerance_pct / 100))
        status = "PASS" if selected and abs(delta) <= allowed_delta else "FAILED"
        results.append({
            "source": source,
            "status": status,
            "profile_rows": profile_rows,
            "lake_rows": lake_rows,
            "delta_rows": delta,
            "allowed_delta_rows": allowed_delta,
            "message": (
                "Profile rows reconcile to selected lake rows within tolerance."
                if status == "PASS"
                else "Profile and selected lake row totals do not reconcile."
            ),
        })
    return results


def channel_anomalies(
    profile_dir: Path,
    target: date,
    sources: list[str],
    baseline_days: int,
    threshold_pct: float,
    min_baseline_days: int,
    min_median_rows: int,
    min_active_ratio: float = 0.7,
) -> tuple[list[dict[str, Any]], list[str]]:
    frame = load_channel_daily(profile_dir)
    warnings: list[str] = []
    required = {"log_date", "source", "channel_name", "raw_ts_chunks"}
    if frame.empty or not required.issubset(frame.columns):
        return [], ["Channel daily mart is unavailable; channel anomaly validation was not run."]
    data = frame.loc[:, sorted(required)].copy()
    data["log_date"] = pd.to_datetime(data["log_date"], errors="coerce")
    data["source"] = data["source"].astype(str).str.lower()
    data["channel_name"] = data["channel_name"].fillna("Unknown / NA").astype(str)
    data["raw_ts_chunks"] = pd.to_numeric(data["raw_ts_chunks"], errors="coerce").fillna(0)
    start = pd.Timestamp(target - timedelta(days=baseline_days))
    end = pd.Timestamp(target)
    data = data[
        data["source"].isin(sources)
        & data["log_date"].between(start, end)
        & ~data["channel_name"].isin(["Unknown / NA", "Others", "Other"])
    ]
    source_history_days = (
        data.loc[data["log_date"] < end]
        .groupby("source", observed=True)["log_date"]
        .nunique()
        .to_dict()
    )
    anomalies: list[dict[str, Any]] = []
    for (source, channel), group in data.groupby(["source", "channel_name"], observed=True):
        target_rows = float(group.loc[group["log_date"] == end, "raw_ts_chunks"].sum())
        history = group.loc[group["log_date"] < end, ["log_date", "raw_ts_chunks"]]
        history = history.groupby("log_date", observed=True)["raw_ts_chunks"].sum()
        nonzero = history[history > 0]
        if len(nonzero) < min_baseline_days:
            continue
        available_days = int(source_history_days.get(source, 0))
        active_ratio = (len(nonzero) / available_days) if available_days else 0.0
        if active_ratio < min_active_ratio:
            continue
        normal = float(median(nonzero.tolist()))
        if normal < min_median_rows:
            continue
        pct = (target_rows / normal * 100) if normal else 0.0
        if pct <= threshold_pct:
            anomalies.append({
                "source": source,
                "channel": channel,
                "date": target.isoformat(),
                "target_raw_ts_chunks": int(target_rows),
                "median_raw_ts_chunks": int(normal),
                "baseline_nonzero_days": int(len(nonzero)),
                "baseline_available_days": available_days,
                "baseline_active_ratio": round(active_ratio, 4),
                "pct_of_normal": round(pct, 2),
                "status": "ANOMALY",
            })
    anomalies.sort(key=lambda row: (row["pct_of_normal"], row["source"], row["channel"]))
    return anomalies, warnings


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temp.replace(path)


def write_source_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source", "status", "message", "root", "day_dir", "files", "rows",
        "start_ist", "end_ist", "start_gap_minutes", "end_gap_minutes",
        "max_internal_gap_minutes", "overlap_minutes", "full_day",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in results:
            selected = item.get("selected") or {}
            writer.writerow({
                "source": item["source"],
                "status": item["status"],
                "message": item["message"],
                "root": selected.get("root", ""),
                "day_dir": selected.get("day_dir", ""),
                "files": len(selected.get("files", [])),
                "rows": selected.get("rows", 0),
                "start_ist": selected.get("start_ist", ""),
                "end_ist": selected.get("end_ist", ""),
                "start_gap_minutes": selected.get("start_gap_minutes", ""),
                "end_gap_minutes": selected.get("end_gap_minutes", ""),
                "max_internal_gap_minutes": selected.get("max_internal_gap_minutes", ""),
                "overlap_minutes": selected.get("overlap_minutes", ""),
                "full_day": selected.get("full_day", False),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate completed daily ETL data before dashboard publication.")
    parser.add_argument("--lake", type=Path, required=True, help="Primary lake root containing source= folders.")
    parser.add_argument("--archive-lake", action="append", default=[], help="Optional archive lake root(s).")
    parser.add_argument("--date", required=True, help="Completed IST date, YYYY-MM-DD.")
    parser.add_argument("--sources", default="fast,stream", help="Comma-separated expected sources.")
    parser.add_argument("--profile-dir", type=Path, default=None, help="Watch-hours profile directory for full mode.")
    parser.add_argument("--mode", choices=["structural", "full"], default="full")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-tolerance-minutes", type=int, default=15)
    parser.add_argument("--end-tolerance-minutes", type=int, default=15)
    parser.add_argument("--max-overlap-minutes", type=int, default=30)
    parser.add_argument("--baseline-days", type=int, default=28)
    parser.add_argument("--channel-threshold-pct", type=float, default=5.0)
    parser.add_argument("--channel-min-baseline-days", type=int, default=3)
    parser.add_argument("--channel-min-median-rows", type=int, default=1000)
    parser.add_argument(
        "--channel-min-active-ratio",
        type=float,
        default=0.7,
        help="Minimum share of available baseline days on which a channel must be active.",
    )
    parser.add_argument("--reconcile-tolerance-pct", type=float, default=0.1)
    parser.add_argument("--reconcile-tolerance-rows", type=int, default=100)
    parser.add_argument("--fail-on-channel-anomaly", action="store_true")
    parser.add_argument("--report-prefix", default="daily_delivery_validation")
    args = parser.parse_args()

    try:
        target = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("--date must be YYYY-MM-DD") from exc
    sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    if not sources:
        raise SystemExit("--sources must include at least one source")
    roots = unique_roots(args.lake.resolve(), archive_roots(args.archive_lake))
    source_results = [
        source_result(
            roots,
            source,
            target,
            args.start_tolerance_minutes,
            args.end_tolerance_minutes,
            args.max_overlap_minutes,
        )
        for source in sources
    ]

    reconciliation: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    warnings: list[str] = []
    if args.mode == "full":
        if args.profile_dir is None:
            raise SystemExit("--profile-dir is required in full mode")
        reconciliation = reconcile_profile(
            source_results,
            args.profile_dir.resolve(),
            target,
            args.reconcile_tolerance_pct,
            args.reconcile_tolerance_rows,
        )
        anomalies, channel_warnings = channel_anomalies(
            args.profile_dir.resolve(),
            target,
            sources,
            args.baseline_days,
            args.channel_threshold_pct,
            args.channel_min_baseline_days,
            args.channel_min_median_rows,
            args.channel_min_active_ratio,
        )
        warnings.extend(channel_warnings)

    hard_failures = [item for item in source_results if item["hard_failure"]]
    hard_failures.extend(item for item in reconciliation if item.get("status") == "FAILED")
    if hard_failures:
        overall_status = "FAIL"
    elif anomalies or warnings:
        overall_status = "REVIEW"
    else:
        overall_status = "PASS"

    generated = datetime.now(IST)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_ist": generated.isoformat(timespec="seconds"),
        "mode": args.mode,
        "date": target.isoformat(),
        "sources": sources,
        "lake_roots": [str(root) for root in roots],
        "overall_status": overall_status,
        "hard_failure_count": len(hard_failures),
        "channel_anomaly_count": len(anomalies),
        "warnings": warnings,
        "source_results": source_results,
        "profile_reconciliation": reconciliation,
        "channel_anomalies": anomalies,
    }
    stamp = generated.strftime("%Y%m%d_%H%M%S")
    prefix = args.report_prefix
    latest_json = args.output_dir / f"{prefix}_latest.json"
    run_json = args.output_dir / f"{prefix}_{target.isoformat()}_{stamp}.json"
    source_csv = args.output_dir / f"{prefix}_{target.isoformat()}_sources.csv"
    anomaly_csv = args.output_dir / f"{prefix}_{target.isoformat()}_channels.csv"
    atomic_write_json(latest_json, payload)
    atomic_write_json(run_json, payload)
    write_source_csv(source_csv, source_results)
    pd.DataFrame(anomalies).to_csv(anomaly_csv, index=False)

    print(f"Daily delivery validation: {overall_status}")
    for item in source_results:
        selected = item.get("selected") or {}
        print(
            f"- {item['source'].upper()}: {item['status']} rows={selected.get('rows', 0):,} "
            f"range={selected.get('start_ist', '')} to {selected.get('end_ist', '')}"
        )
        if item["status"] != "PASS":
            print(f"  {item['message']}")
    if reconciliation:
        for item in reconciliation:
            if item.get("source"):
                print(
                    f"- {item['source'].upper()} profile reconciliation: {item['status']} "
                    f"delta={item.get('delta_rows', 0):,}"
                )
    print(f"Channel anomalies: {len(anomalies)}")
    print(f"Report: {latest_json}")

    if hard_failures or (args.fail_on_channel_anomaly and anomalies):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
