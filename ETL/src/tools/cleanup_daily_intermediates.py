#!/usr/bin/env python3
"""Remove a validated daily ETL's disposable inputs and stage artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq


IST = ZoneInfo("Asia/Kolkata")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "source"


def lake_prefixes(source: str, source_id: str) -> tuple[str, str]:
    source_slug = safe_slug(source)
    source_id_slug = safe_slug(source_id)
    source_prefix = f"{source_slug}_"
    batch_slug = (
        source_id_slug[len(source_prefix) :]
        if source_id_slug.startswith(source_prefix)
        else source_id_slug
    )
    return f"part_{source_slug}_{batch_slug}", f"src_{source_id_slug}"


def parquet_rows(path: Path) -> int:
    if not path.is_file() or path.stat().st_size <= 0:
        return 0
    return int(pq.ParquetFile(path).metadata.num_rows or 0)


def source_lake_rows(
    lake_roots: list[Path],
    source: str,
    source_id: str,
    raw_date: date,
) -> tuple[int, list[Path]]:
    files_by_relative_path: dict[Path, Path] = {}
    # A UTC raw day can only contribute to IST lake partitions D and D+1.
    for lake_root in lake_roots:
        for lake_date in (raw_date, raw_date + timedelta(days=1)):
            day_dir = (
                lake_root
                / f"source={source}"
                / f"year={lake_date:%Y}"
                / f"month={lake_date:%m}"
                / f"day={lake_date:%d}"
            )
            if not day_dir.is_dir():
                continue
            for prefix in lake_prefixes(source, source_id):
                for path in day_dir.glob(f"{prefix}_*.parquet"):
                    if not path.is_file():
                        continue
                    relative_path = path.relative_to(lake_root)
                    existing = files_by_relative_path.get(relative_path)
                    if existing is not None and existing.resolve() != path.resolve():
                        raise SystemExit(
                            "Cleanup refused: duplicate retained lake partition exists in multiple roots: "
                            f"{relative_path}"
                        )
                    files_by_relative_path[relative_path] = path
    ordered = sorted(files_by_relative_path.values())
    return sum(parquet_rows(path) for path in ordered), ordered


def etl_state_rows(path: Path, source: str, source_id: str) -> int:
    if not path.is_file():
        raise SystemExit(f"Cleanup refused: ETL state is missing: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    key = f"{source_id}_final_clean.parquet"
    entry = state.get(key)
    if not isinstance(entry, dict):
        raise SystemExit(f"Cleanup refused: ETL state has no successful record for {key}.")
    if entry.get("status") != "ok" or entry.get("source_key") != source:
        raise SystemExit(f"Cleanup refused: ETL state is not successful for {key}.")
    rows = int(entry.get("rows") or 0)
    if rows <= 0:
        raise SystemExit(f"Cleanup refused: ETL state has no positive row count for {key}.")
    return rows


def load_validation_report(path: Path, target_date: str, sources: list[str]) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Cleanup refused: validation report is missing: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("date") != target_date:
        raise SystemExit(
            "Cleanup refused: validation report date does not match "
            f"({report.get('date')!r} != {target_date!r})."
        )
    if report.get("mode") != "full" or report.get("overall_status") != "PASS":
        raise SystemExit("Cleanup refused: a full PASS validation report is required.")
    if int(report.get("hard_failure_count") or 0) != 0:
        raise SystemExit("Cleanup refused: validation report contains hard failures.")

    source_results = {str(row.get("source", "")).lower(): row for row in report.get("source_results", [])}
    reconciliations = {
        str(row.get("source", "")).lower(): row
        for row in report.get("profile_reconciliation", [])
    }
    for source in sources:
        result = source_results.get(source)
        selected = (result or {}).get("selected") or {}
        if not result or result.get("status") != "PASS" or not selected.get("full_day"):
            raise SystemExit(f"Cleanup refused: {source} does not have validated full-day coverage.")
        reconciliation = reconciliations.get(source)
        if (
            not reconciliation
            or reconciliation.get("status") != "PASS"
            or int(reconciliation.get("delta_rows") or 0) != 0
        ):
            raise SystemExit(f"Cleanup refused: {source} profile reconciliation is not an exact match.")
    return report


def ensure_within(path: Path, root: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise SystemExit(f"Cleanup refused: path escapes its expected root: {path}")


def inspect_artifact_group(
    source: str,
    category: str,
    root: Path,
    allowed_suffix: str,
    allow_subdirs: bool = True,
    allowed_names: set[str] | None = None,
    delete_root: bool = True,
) -> dict[str, Any]:
    count = 0
    total_bytes = 0
    matching_paths: list[str] = []
    if not root.exists():
        return {
            "source": source,
            "category": category,
            "root": str(root),
            "file_count": 0,
            "bytes": 0,
            "delete_strategy": "directory" if delete_root else "files",
        }
    if root.is_symlink() or not root.is_dir():
        raise SystemExit(f"Cleanup refused: artifact root is not a normal directory: {root}")

    for directory, dir_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        if not allow_subdirs and directory_path != root:
            raise SystemExit(f"Cleanup refused: unexpected subdirectory under {root}: {directory_path}")
        for dir_name in dir_names:
            child = directory_path / dir_name
            if child.is_symlink():
                raise SystemExit(f"Cleanup refused: artifact directory is a symlink: {child}")
        for file_name in file_names:
            path = directory_path / file_name
            if path.is_symlink():
                raise SystemExit(f"Cleanup refused: artifact is a symlink: {path}")
            if not file_name.lower().endswith(allowed_suffix):
                if delete_root:
                    raise SystemExit(f"Cleanup refused: unexpected file under {root}: {path}")
                continue
            if allowed_names is not None and (directory_path != root or file_name not in allowed_names):
                raise SystemExit(f"Cleanup refused: unexpected final-clean file: {path}")
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue
            count += 1
            total_bytes += size
            if not delete_root:
                matching_paths.append(str(path))
    group = {
        "source": source,
        "category": category,
        "root": str(root),
        "file_count": count,
        "bytes": total_bytes,
        "delete_strategy": "directory" if delete_root else "files",
    }
    if matching_paths:
        group["files"] = matching_paths
    return group


def artifact_groups(
    base_root: Path,
    raw_root: Path,
    target_date: str,
    source_names: dict[str, str],
) -> list[dict[str, Any]]:
    year, month, day = target_date.split("-")
    groups: list[dict[str, Any]] = []

    for source, folder_name in source_names.items():
        source_id = f"{source}_{year}_{month}_{day}"
        parquet_dir = base_root / "stage" / "parquet" / f"source={source}" / f"year={year}" / f"month={month}" / f"day={day}"
        final_dir = base_root / "stage" / "final_clean" / f"source={source}" / f"year={year}" / f"month={month}" / f"day={day}"
        final_file = final_dir / f"{source_id}_final_clean.parquet"
        raw_dir = raw_root / folder_name / month / day
        ensure_within(parquet_dir, base_root / "stage")
        ensure_within(final_file, base_root / "stage")
        ensure_within(raw_dir, raw_root / folder_name)
        groups.extend(
            [
                inspect_artifact_group(
                    source,
                    "stage_parquet",
                    parquet_dir,
                    ".parquet",
                    delete_root=False,
                ),
                inspect_artifact_group(
                    source,
                    "final_clean",
                    final_dir,
                    ".parquet",
                    allow_subdirs=False,
                    allowed_names={final_file.name},
                ),
                inspect_artifact_group(source, "raw_gz", raw_dir, ".gz"),
            ]
        )
    return groups


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(path)


def prune_empty_parents(start: Path, stop: Path) -> None:
    current = start
    stop = stop.resolve(strict=False)
    while current.exists() and current.resolve(strict=False) != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="ETL data root containing stage/ and lake/.")
    parser.add_argument("--lake", required=True, help="Validated lake root retained after cleanup.")
    parser.add_argument(
        "--archive-lake",
        action="append",
        default=[],
        help="Additional retained lake root; may be supplied more than once.",
    )
    parser.add_argument(
        "--etl3-state",
        help="03.py state JSON used as row evidence when final-clean has already been removed.",
    )
    parser.add_argument("--raw-root", required=True, help="Raw root containing the source folders.")
    parser.add_argument("--date", required=True, help="Processed date in YYYY-MM-DD format.")
    parser.add_argument("--sources", default="fast,stream", help="Comma-separated daily sources.")
    parser.add_argument("--stream-name", default="Veto Stream Backup")
    parser.add_argument("--fast-name", default="Veto fast Backup")
    parser.add_argument("--validation-report", required=True)
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--execute", action="store_true", help="Delete files; otherwise only write a dry-run plan.")
    args = parser.parse_args()

    try:
        target_date = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("--date must be YYYY-MM-DD") from exc

    sources = [value.strip().lower() for value in args.sources.split(",") if value.strip()]
    unsupported = sorted(set(sources) - {"fast", "stream"})
    if not sources or unsupported:
        raise SystemExit(f"Unsupported cleanup source(s): {', '.join(unsupported) or 'none'}")

    base_root = Path(args.base).expanduser().resolve()
    lake_root = Path(args.lake).expanduser().resolve()
    archive_lake_roots = [Path(value).expanduser().resolve() for value in args.archive_lake]
    lake_roots = [lake_root, *archive_lake_roots]
    raw_root = Path(args.raw_root).expanduser().resolve()
    validation_path = Path(args.validation_report).expanduser().resolve()
    audit_dir = Path(args.audit_dir).expanduser().resolve()
    etl3_state_path = Path(args.etl3_state).expanduser().resolve() if args.etl3_state else None
    ensure_within(lake_root, base_root)
    for root in lake_roots:
        if not root.is_dir():
            raise SystemExit(f"Cleanup refused: retained lake root is missing: {root}")
    report = load_validation_report(validation_path, args.date, sources)

    source_names = {"fast": args.fast_name, "stream": args.stream_name}
    checks: list[dict[str, Any]] = []
    for source in sources:
        print(f"Validating {source} final-clean rows against retained lake...", flush=True)
        source_id = f"{source}_{args.date.replace('-', '_')}"
        final_file = (
            base_root
            / "stage"
            / "final_clean"
            / f"source={source}"
            / f"year={args.date[0:4]}"
            / f"month={args.date[5:7]}"
            / f"day={args.date[8:10]}"
            / f"{source_id}_final_clean.parquet"
        )
        if final_file.is_file():
            evidence_type = "final_clean"
            evidence_path = final_file
            evidence_rows = parquet_rows(final_file)
        elif etl3_state_path is not None:
            evidence_type = "etl3_state"
            evidence_path = etl3_state_path
            evidence_rows = etl_state_rows(etl3_state_path, source, source_id)
        else:
            raise SystemExit(f"Cleanup refused: final-clean evidence is missing: {final_file}")
        lake_rows, lake_files = source_lake_rows(lake_roots, source, source_id, target_date)
        if evidence_rows <= 0 or evidence_rows != lake_rows:
            raise SystemExit(
                f"Cleanup refused: {source} {evidence_type}/lake mismatch "
                f"({evidence_rows:,} != {lake_rows:,})."
            )
        checks.append(
            {
                "source": source,
                "source_id": source_id,
                "evidence_type": evidence_type,
                "evidence_path": str(evidence_path),
                "evidence_rows": evidence_rows,
                "lake_rows": lake_rows,
                "lake_files": [str(path) for path in lake_files],
            }
        )

    print("Enumerating date-scoped raw and stage artifacts...", flush=True)
    selected_source_names = {source: source_names[source] for source in sources}
    groups = artifact_groups(base_root, raw_root, args.date, selected_source_names)
    started = datetime.now(IST)
    stamp = started.strftime("%Y%m%d_%H%M%S_%f")
    manifest_path = audit_dir / f"cleanup_{args.date}_{stamp}.json"
    total_files = sum(int(group["file_count"]) for group in groups)
    total_bytes = sum(int(group["bytes"]) for group in groups)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "date": args.date,
        "started_at_ist": started.isoformat(timespec="seconds"),
        "mode": "execute" if args.execute else "dry-run",
        "status": "planned",
        "validation_report": str(validation_path),
        "validation_generated_at_ist": report.get("generated_at_ist"),
        "lake_roots": [str(path) for path in lake_roots],
        "checks": checks,
        "file_count": total_files,
        "planned_bytes": total_bytes,
        "groups": groups,
    }
    write_json_atomic(manifest_path, manifest)

    if not args.execute:
        manifest["status"] = "dry-run-complete"
        manifest["finished_at_ist"] = datetime.now(IST).isoformat(timespec="seconds")
        write_json_atomic(manifest_path, manifest)
        print(f"Cleanup dry run: {total_files:,} files, {total_bytes / (1024 ** 3):,.2f} GiB")
        print(f"Manifest: {manifest_path}")
        return

    deleted_bytes = 0
    deleted_count = 0
    try:
        for group in groups:
            root = Path(group["root"])
            if group["delete_strategy"] == "files":
                for raw_path in group.get("files", []):
                    path = Path(raw_path)
                    if path.is_symlink():
                        raise RuntimeError(f"Refusing to delete a symlink: {path}")
                    if path.exists():
                        path.unlink()
                deleted_count += int(group["file_count"])
                deleted_bytes += int(group["bytes"])
                group["deleted"] = all(not Path(path).exists() for path in group.get("files", []))
                stop = base_root / "stage" / "parquet"
                prune_empty_parents(root, stop)
                continue
            if root.exists():
                if root.is_symlink() or not root.is_dir():
                    raise RuntimeError(f"Refusing to delete a non-directory artifact root: {root}")
                shutil.rmtree(root)
                deleted_count += int(group["file_count"])
                deleted_bytes += int(group["bytes"])
            group["deleted"] = not root.exists()
            if group["category"] == "raw_gz":
                stop = raw_root / source_names[group["source"]]
            elif group["category"] == "final_clean":
                stop = base_root / "stage" / "final_clean"
            else:
                stop = base_root / "stage" / "parquet"
            prune_empty_parents(root.parent, stop)
    except Exception as exc:
        manifest["status"] = "partial-failure"
        manifest["error"] = str(exc)
        manifest["deleted_count"] = deleted_count
        manifest["deleted_bytes"] = deleted_bytes
        manifest["finished_at_ist"] = datetime.now(IST).isoformat(timespec="seconds")
        write_json_atomic(manifest_path, manifest)
        raise

    manifest["status"] = "complete"
    manifest["deleted_count"] = deleted_count
    manifest["deleted_bytes"] = deleted_bytes
    manifest["finished_at_ist"] = datetime.now(IST).isoformat(timespec="seconds")
    write_json_atomic(manifest_path, manifest)
    print(f"Cleanup complete: {deleted_count:,} files, {deleted_bytes / (1024 ** 3):,.2f} GiB reclaimed")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
