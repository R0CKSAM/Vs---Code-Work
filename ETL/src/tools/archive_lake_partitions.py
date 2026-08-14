#!/usr/bin/env python3
"""Safely tier completed lake partitions from the hot lake to an archive lake."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq


IST = ZoneInfo("Asia/Kolkata")


def parquet_metadata(path: Path) -> dict[str, Any]:
    metadata = pq.read_metadata(path)
    minimums: list[float] = []
    maximums: list[float] = []
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            if column.path_in_schema != "reqTimeSec" or column.statistics is None:
                continue
            try:
                minimums.append(float(column.statistics.min))
                maximums.append(float(column.statistics.max))
            except (TypeError, ValueError):
                continue
    coverage = max(maximums) - min(minimums) if minimums and maximums else 0.0
    return {
        "bytes": int(path.stat().st_size),
        "rows": int(metadata.num_rows or 0),
        "coverage_seconds": round(coverage, 6),
    }


def quality(metadata: dict[str, Any]) -> tuple[float, int, int]:
    return (
        float(metadata["coverage_seconds"]),
        int(metadata["rows"]),
        int(metadata["bytes"]),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def partition_date(path: Path) -> date:
    values = {
        piece.split("=", 1)[0].lower(): piece.split("=", 1)[1]
        for piece in path.parts
        if "=" in piece
    }
    return date(int(values["year"]), int(values["month"]), int(values["day"]))


def ensure_separate_roots(source_root: Path, archive_root: Path) -> None:
    if source_root == archive_root:
        raise SystemExit("Source and archive lake roots must be different.")
    if source_root.is_relative_to(archive_root) or archive_root.is_relative_to(source_root):
        raise SystemExit("Source and archive lake roots must not contain one another.")


def prune_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current.exists() and current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def copy_verified(source: Path, destination: Path, verify_hash: bool) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".archiving")
    temporary.unlink(missing_ok=True)
    shutil.copy2(source, temporary)
    source_metadata = parquet_metadata(source)
    copied_metadata = parquet_metadata(temporary)
    if source_metadata != copied_metadata:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Copied Parquet metadata mismatch: {source} -> {destination}")
    source_hash = None
    if verify_hash:
        source_hash = sha256(source)
        if source_hash != sha256(temporary):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Copied file hash mismatch: {source} -> {destination}")
    os.replace(temporary, destination)
    return {"metadata": copied_metadata, "sha256": source_hash}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--through", required=True, help="Archive partition dates through YYYY-MM-DD.")
    parser.add_argument("--sources", default="fast,stream")
    parser.add_argument("--quarantine-root", required=True)
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--pipeline-lock")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--skip-hash", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    archive_root = Path(args.archive_root).expanduser().resolve()
    quarantine_root = Path(args.quarantine_root).expanduser().resolve()
    audit_dir = Path(args.audit_dir).expanduser().resolve()
    through = date.fromisoformat(args.through)
    sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    if set(sources) - {"fast", "stream"}:
        raise SystemExit("Only fast and stream lake sources are supported.")
    if not source_root.is_dir() or not archive_root.is_dir():
        raise SystemExit("Both source and archive lake roots must already exist.")
    ensure_separate_roots(source_root, archive_root)
    if args.pipeline_lock and Path(args.pipeline_lock).exists():
        raise SystemExit(f"Archive refused while pipeline lock exists: {args.pipeline_lock}")

    candidates: list[Path] = []
    for source in sources:
        for path in (source_root / f"source={source}").glob("year=*/month=*/day=*/part_*.parquet"):
            if partition_date(path) <= through:
                candidates.append(path)
    candidates.sort(key=lambda path: str(path).casefold())

    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S_%f")
    audit_path = audit_dir / f"lake_archive_{stamp}.json"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "mode": "execute" if args.execute else "dry-run",
        "started_at_ist": datetime.now(IST).isoformat(timespec="seconds"),
        "source_root": str(source_root),
        "archive_root": str(archive_root),
        "through": through.isoformat(),
        "status": "running",
        "files": [],
    }
    atomic_json(audit_path, payload)

    moved_bytes = 0
    try:
        for index, source in enumerate(candidates, start=1):
            relative = source.relative_to(source_root)
            destination = archive_root / relative
            source_metadata = parquet_metadata(source)
            action = "copy-new"
            destination_metadata = None
            equal_content = False
            if destination.exists():
                destination_metadata = parquet_metadata(destination)
                source_quality = quality(source_metadata)
                destination_quality = quality(destination_metadata)
                if destination_quality > source_quality:
                    action = "keep-better-archive"
                elif destination_quality == source_quality:
                    equal_content = sha256(source) == sha256(destination)
                    action = "keep-identical-archive" if equal_content else "replace-equal-conflict"
                else:
                    action = "replace-with-hot-winner"

            record = {
                "source": str(source),
                "destination": str(destination),
                "source_metadata": source_metadata,
                "destination_metadata_before": destination_metadata,
                "action": action,
                "status": "planned",
            }
            payload["files"].append(record)
            print(f"[{index}/{len(candidates)}] {action}: {relative}", flush=True)
            if not args.execute:
                continue

            if action.startswith("replace-"):
                quarantine = quarantine_root / stamp / relative
                quarantine.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, quarantine)
                record["quarantined"] = str(quarantine)
                try:
                    verification = copy_verified(source, destination, not args.skip_hash)
                except Exception:
                    destination.unlink(missing_ok=True)
                    os.replace(quarantine, destination)
                    raise
                record["verification"] = verification
            elif action == "copy-new":
                record["verification"] = copy_verified(source, destination, not args.skip_hash)

            final_metadata = parquet_metadata(destination)
            if quality(final_metadata) < quality(source_metadata):
                raise RuntimeError(f"Archive is less complete than hot file after transfer: {destination}")
            source.unlink()
            prune_empty_parents(source.parent, source_root)
            moved_bytes += int(source_metadata["bytes"])
            record["destination_metadata_after"] = final_metadata
            record["status"] = "archived-and-hot-removed"
            atomic_json(audit_path, payload)

        if args.execute:
            for source in sources:
                prune_empty_parents(source_root / f"source={source}", source_root)
        payload["status"] = "complete" if args.execute else "dry-run-complete"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
        raise
    finally:
        payload["finished_at_ist"] = datetime.now(IST).isoformat(timespec="seconds")
        payload["candidate_files"] = len(candidates)
        payload["moved_bytes"] = moved_bytes
        atomic_json(audit_path, payload)

    print(f"Archive status: {payload['status']}")
    print(f"Candidate files: {len(candidates):,}")
    print(f"Hot bytes removed: {moved_bytes / 1024**3:,.2f} GiB")
    print(f"Audit: {audit_path}")


if __name__ == "__main__":
    main()
