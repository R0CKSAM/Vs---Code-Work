"""Stage only raw files added or changed since a prior micro-batch manifest."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def manifest_key(item: dict[str, Any]) -> tuple[str, int] | None:
    """Return a staging-root-independent identity for a raw input file."""
    value = item.get("relative_path") or item.get("path")
    if not value or item.get("bytes") is None:
        return None
    # Absolute paths vary between benchmark workspaces; the source-relative path
    # plus byte size is stable across every micro-batch staging directory.
    normalised = str(value).replace("\\", "/")
    # The first benchmark manifest predates ``relative_path``. Recover the
    # source-relative identity from its legacy absolute path for compatibility.
    marker = "/Veto Logs Backup/"
    if marker in normalised:
        normalised = normalised.rsplit(marker, maxsplit=1)[1]
    return normalised, int(item["bytes"])


def read_manifest(path: Path) -> set[tuple[str, int]]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {key for item in payload.get("files", []) if (key := manifest_key(item))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument(
        "--baseline-manifest",
        type=Path,
        action="append",
        required=True,
        help="Processed manifest; repeat this option to combine prior micro-batches.",
    )
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()

    raw_root = args.raw_root.expanduser().resolve()
    baseline_paths = [path.expanduser().resolve() for path in args.baseline_manifest]
    out_root = args.out_root.expanduser().resolve()
    if not raw_root.is_dir():
        raise SystemExit(f"Raw root not found: {raw_root}")
    for baseline_path in baseline_paths:
        if not baseline_path.is_file():
            raise SystemExit(f"Baseline manifest not found: {baseline_path}")

    baseline = set().union(*(read_manifest(path) for path in baseline_paths))
    delta: list[dict[str, Any]] = []
    for path in raw_root.rglob("*.gz"):
        size = path.stat().st_size
        key = (str(path.relative_to(raw_root)).replace("\\", "/"), size)
        if key in baseline:
            continue
        relative = path.relative_to(raw_root)
        destination = out_root / "raw" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            try:
                os.link(path, destination)
            except OSError as exc:
                raise RuntimeError(f"Could not hard-link delta file: {path}") from exc
        delta.append(
            {
                "path": str(path),
                "relative_path": str(relative),
                "bytes": size,
                "last_write_utc": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        )

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "baseline_manifests": [str(path) for path in baseline_paths],
        "new_or_changed_file_count": len(delta),
        "new_or_changed_bytes": sum(item["bytes"] for item in delta),
        "files": delta,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = out_root / "delta_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Delta files: {len(delta):,}")
    print(f"Delta bytes: {manifest['new_or_changed_bytes'] / 1_000_000:.1f} MB")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
