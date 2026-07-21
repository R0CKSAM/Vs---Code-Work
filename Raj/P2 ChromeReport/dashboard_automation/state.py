from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_processed_state(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {"version": 1, "processed_files": {}}
    return json.loads(file_path.read_text(encoding="utf-8"))


def save_processed_state(file_path: Path, state: dict[str, Any]) -> None:
    file_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_processed(state: dict[str, Any], fingerprint: str) -> bool:
    return fingerprint in state.get("processed_files", {})


def mark_processed(
    state: dict[str, Any],
    fingerprint: str,
    file_path: Path,
    week_label: str,
    row_counts: dict[str, int],
) -> None:
    state.setdefault("processed_files", {})[fingerprint] = {
        "file_name": file_path.name,
        "file_path": str(file_path.resolve()),
        "week": week_label,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "row_counts": row_counts,
    }
