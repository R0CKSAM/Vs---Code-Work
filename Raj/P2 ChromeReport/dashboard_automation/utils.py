from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Iterable

import pandas as pd


WEEK_PATTERNS = (
    re.compile(r"wk[-\s_]*(?P<week>\d{1,2}).*?(?P<year>20\d{2})", re.IGNORECASE),
    re.compile(r"(?P<year>20\d{2}).*?wk[-\s_]*(?P<week>\d{1,2})", re.IGNORECASE),
)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_header(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", normalize_text(value).upper())


def extract_week_label(file_name: str) -> str:
    for pattern in WEEK_PATTERNS:
        match = pattern.search(file_name)
        if match:
            week = int(match.group("week"))
            year = match.group("year")[-2:]
            return f"Wk-{week:02d}'{year}"
    raise ValueError(f"Could not extract week from filename: {file_name}")


def compute_file_hash(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def list_candidate_files(data_dir: Path, supported_extensions: Iterable[str]) -> list[Path]:
    allowed = {extension.lower() for extension in supported_extensions}
    return sorted(
        [
            path
            for path in data_dir.iterdir()
            if path.is_file() and not path.name.startswith("~$") and path.suffix.lower() in allowed
        ],
        key=lambda path: path.name.lower(),
    )


def wait_for_file_ready(file_path: Path, retries: int = 12, delay_seconds: float = 1.0) -> None:
    last_size = -1
    stable_count = 0
    for _attempt in range(retries):
        if not file_path.exists():
            time.sleep(delay_seconds)
            continue
        current_size = file_path.stat().st_size
        if current_size > 0 and current_size == last_size:
            stable_count += 1
            if stable_count >= 2:
                return
        else:
            stable_count = 0
        last_size = current_size
        time.sleep(delay_seconds)
    raise TimeoutError(f"File did not become stable in time: {file_path}")


def find_header_row(
    file_path: Path,
    sheet_name: str,
    required_aliases: dict[str, tuple[str, ...]],
    max_scan_rows: int = 25,
) -> int:
    preview = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=None,
        nrows=max_scan_rows,
        engine="openpyxl",
    )
    for row_index in range(len(preview.index)):
        normalized_values = {normalize_header(value) for value in preview.iloc[row_index].tolist() if normalize_text(value)}
        if not normalized_values:
            continue
        if all(any(alias in normalized_values for alias in aliases) for aliases in required_aliases.values()):
            return row_index
    raise ValueError(f"Could not detect header row in sheet '{sheet_name}' for {file_path.name}")
