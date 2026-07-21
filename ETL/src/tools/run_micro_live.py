"""Append-only micro ETL runner with one persistent dashboard output.

Each completed micro batch receives a unique source ID. The normal pipeline can
therefore append same-day lake parts without replacing an earlier batch. A raw
file manifest is committed only after the pipeline succeeds, so interrupted
runs are safe to retry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


SOURCE_FOLDERS = {
    "stream": "Veto Stream Backup",
    "fast": "Veto fast Backup",
}
RAW_ROOT_MARKER = "/Veto Logs Backup/"


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not slug:
        raise ValueError("batch ID must contain at least one letter or number")
    return slug


def canonical_relative_path(value: str) -> str:
    """Normalize both legacy absolute and current source-relative manifests."""
    normalised = re.sub(r"/+", "/", str(value).replace("\\", "/"))
    if RAW_ROOT_MARKER in normalised:
        normalised = normalised.rsplit(RAW_ROOT_MARKER, maxsplit=1)[1]
    return normalised.lstrip("/")


def manifest_entries(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for item in payload.get("files", []):
        value = item.get("relative_path") or item.get("path")
        size = item.get("bytes")
        if not value or size is None:
            continue
        entries.append(
            {
                "relative_path": canonical_relative_path(str(value)),
                "bytes": int(size),
            }
        )
    return entries


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "files": [], "batches": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Micro state is not a JSON object: {path}")
    payload.setdefault("schema_version", 1)
    payload.setdefault("files", [])
    payload.setdefault("batches", [])
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Existing file has a different size: {destination}")
        return "existing"
    try:
        os.link(source, destination)
        return "linked"
    except OSError:
        # A copy is the safe fallback when paths are on different volumes.
        shutil.copy2(source, destination)
        return "copied"


def state_keys(entries: Iterable[dict[str, Any]]) -> set[tuple[str, int]]:
    return {
        (canonical_relative_path(str(item["relative_path"])), int(item["bytes"]))
        for item in entries
        if item.get("relative_path") and item.get("bytes") is not None
    }


def discover_delta(raw_root: Path, target_date: date, sources: list[str], known: set[tuple[str, int]]) -> list[dict[str, Any]]:
    month = target_date.strftime("%m")
    day = target_date.strftime("%d")
    delta: list[dict[str, Any]] = []
    for source in sources:
        source_root = raw_root / SOURCE_FOLDERS[source] / month / day
        if not source_root.is_dir():
            raise FileNotFoundError(f"Raw {source} day folder not found: {source_root}")
        for path in source_root.rglob("*.gz"):
            relative_path = canonical_relative_path(str(path.relative_to(raw_root)))
            size = path.stat().st_size
            if (relative_path, size) not in known:
                delta.append({"relative_path": relative_path, "bytes": size, "source_path": str(path)})
    return sorted(delta, key=lambda item: item["relative_path"])


def stage_delta(entries: list[dict[str, Any]], raw_root: Path, batch_raw_root: Path) -> tuple[int, int]:
    linked = copied = 0
    for item in entries:
        source = raw_root / Path(item["relative_path"])
        destination = batch_raw_root / Path(item["relative_path"])
        result = link_or_copy(source, destination)
        linked += result == "linked"
        copied += result == "copied"
    return linked, copied


def bootstrap_run(workspace: Path, run_root: Path, state: dict[str, Any]) -> tuple[int, int]:
    """Import immutable lake parts and raw manifests from a prior benchmark run."""
    manifest = run_root / "selection_manifest.json"
    if not manifest.exists():
        manifest = run_root / "delta_manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(f"No selection or delta manifest in: {run_root}")

    label = safe_slug(run_root.name)
    linked = copied = 0
    lake_root = run_root / "data" / "lake"
    if not lake_root.is_dir():
        raise FileNotFoundError(f"Benchmark lake not found: {lake_root}")
    for source_part in lake_root.rglob("*.parquet"):
        relative = source_part.relative_to(lake_root)
        destination = workspace / "data" / "lake" / relative.with_name(
            f"{source_part.stem}_{label}{source_part.suffix}"
        )
        result = link_or_copy(source_part, destination)
        linked += result == "linked"
        copied += result == "copied"

    known = state_keys(state["files"])
    added = 0
    for entry in manifest_entries(manifest):
        key = (entry["relative_path"], entry["bytes"])
        if key not in known:
            state["files"].append(entry)
            known.add(key)
            added += 1
    state["batches"].append(
        {
            "batch_id": label,
            "kind": "bootstrap",
            "run_root": str(run_root),
            "raw_files_added": added,
            "imported_at": datetime.now().astimezone().isoformat(),
        }
    )
    return linked, copied


def run_pipeline(
    etl_root: Path,
    workspace: Path,
    batch_raw_root: Path | None,
    target_date: date,
    batch_id: str | None,
    sources: str,
    refresh_device_snapshot: bool,
    refresh_identity_marts: bool,
) -> None:
    command = [
        str(etl_root.parent / "venv" / "Scripts" / "python.exe"),
        str(etl_root / "src" / "orchestrator" / "run_pipeline.py"),
        "--base", str(workspace / "data"),
        "--output-root", str(workspace / "output"),
        "--overview-lake-root", str(workspace / "data" / "lake"),
        "--skip-overview",
        "--skip-master",
        "--deep-profile-mode", "full",
        "--deep-profile-threads", "4",
        "--deep-profile-memory", "16GB",
        "--concurrency-window-days", "1",
        "--latency-window-days", "1",
        "--state-name", "micro_live",
    ]
    if not refresh_device_snapshot:
        # The snapshot resolves archive lakes and is a 40+ minute job. Keep it
        # in a separate slow lane so an otherwise small micro batch stays small.
        command.append("--skip-device-snapshot")
    if not refresh_identity_marts:
        # These derive historical device/session data through archive roots.
        # They are refreshed in the slow lane to keep micro dashboards truthful
        # and prevent an unnoticed full-history scan on every batch.
        command.extend(["--skip-identity-mart", "--skip-content-mart", "--skip-audience"])
    if batch_raw_root is None:
        command.append("--skip-etl")
    else:
        command.extend(
            [
                "--etl1-daily-date", target_date.isoformat(),
                "--etl1-batch-id", batch_id or "batch",
                "--etl1-daily-raw-root", str(batch_raw_root),
                "--etl1-sources", sources,
                "--etl1-workers", "2",
                "--etl1-compression", "zstd",
                "--lake-repair-lookback-days", "0",
            ]
        )
    print("Running persistent micro pipeline:")
    print(" ".join(f'"{part}"' if " " in part else part for part in command))
    subprocess.run(command, check=True, cwd=etl_root)


def main() -> None:
    etl_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, required=True, help="IST date to process")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=etl_root / "data" / "raw" / "Veto Logs Backup",
        help="Raw root containing Veto Stream Backup and Veto fast Backup",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=etl_root / "output" / "micro_live",
        help="Persistent micro ETL workspace",
    )
    parser.add_argument("--sources", choices=["both", "stream", "fast"], default="both")
    parser.add_argument("--batch-id", default=None, help="Stable batch ID; defaults to current IST timestamp")
    parser.add_argument(
        "--refresh-device-snapshot",
        action="store_true",
        help="Also run the slower archive-aware device snapshot refresh.",
    )
    parser.add_argument(
        "--refresh-identity-marts",
        action="store_true",
        help="Also refresh archive-aware identity, content, and Audience Operations marts.",
    )
    parser.add_argument(
        "--bootstrap-run-root",
        type=Path,
        action="append",
        default=[],
        help="Prior isolated benchmark root to import; can be repeated",
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    raw_root = args.raw_root.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_path = workspace / "state" / "processed_raw_manifest.json"
    state = read_state(state_path)

    for run_root in args.bootstrap_run_root:
        linked, copied = bootstrap_run(workspace, run_root.expanduser().resolve(), state)
        print(f"Bootstrapped {run_root}: linked={linked:,}, copied={copied:,}")

    if args.bootstrap_run_root:
        atomic_write_json(state_path, state)
        run_pipeline(
            etl_root, workspace, None, args.date, None, args.sources,
            args.refresh_device_snapshot, args.refresh_identity_marts,
        )
        print(f"Persistent dashboards: {workspace / 'output'}")
        return

    sources = ["stream", "fast"] if args.sources == "both" else [args.sources]
    known = state_keys(state["files"])
    delta = discover_delta(raw_root, args.date, sources, known)
    if not delta:
        print("No new raw files. Persistent dashboards were not regenerated.")
        return

    batch_id = safe_slug(args.batch_id or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S"))
    batch_root = workspace / "batches" / batch_id
    batch_raw_root = batch_root / "raw" / "Veto Logs Backup"
    linked, copied = stage_delta(delta, raw_root, batch_raw_root)
    atomic_write_json(
        batch_root / "batch_manifest.json",
        {
            "batch_id": batch_id,
            "target_date_ist": args.date.isoformat(),
            "created_at": datetime.now().astimezone().isoformat(),
            "files": [{"relative_path": item["relative_path"], "bytes": item["bytes"]} for item in delta],
        },
    )
    print(f"Staged raw delta: files={len(delta):,}, linked={linked:,}, copied={copied:,}")
    run_pipeline(
        etl_root, workspace, batch_raw_root, args.date, batch_id, args.sources,
        args.refresh_device_snapshot, args.refresh_identity_marts,
    )

    state["files"].extend({"relative_path": item["relative_path"], "bytes": item["bytes"]} for item in delta)
    state["batches"].append(
        {
            "batch_id": batch_id,
            "kind": "incremental",
            "target_date_ist": args.date.isoformat(),
            "raw_files_added": len(delta),
            "completed_at": datetime.now().astimezone().isoformat(),
        }
    )
    atomic_write_json(state_path, state)
    print(f"Persistent dashboards: {workspace / 'output'}")


if __name__ == "__main__":
    main()
