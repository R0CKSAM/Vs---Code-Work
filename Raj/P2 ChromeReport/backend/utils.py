from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DIMENSION_COLUMNS = [
    "Market",
    "MSO",
    "City",
    "Head End",
    "Channel Name",
    "CR No",
    "Transmission",
    "MSO Type",
    "Band",
    "TV Channel No",
]

FILTER_COLUMNS = [
    "Market",
    "MSO",
    "City",
    "Head End",
    "Channel Name",
    "CR No",
    "Transmission",
    "MSO Type",
    "Band",
    "TV Channel No",
]

BUSINESS_KEY_COLUMNS = [
    "Market",
    "MSO",
    "City",
    "Head End",
    "Channel Name",
    "CR No",
]

COLUMN_ALIASES = {
    "mso": "MSO",
    "market": "Market",
    "mso_type": "MSO Type",
    "city": "City",
    "head_end": "Head End",
    "channel_name": "Channel Name",
    "channel": "Channel Name",
    "transmission": "Transmission",
    "transmission_band": "Transmission",
    "band": "Band",
    "tv_channel_no": "TV Channel No",
    "tv_ch_no": "TV Channel No",
    "cr_no": "CR No",
    "crn_no": "CR No",
    "frequency": "Frequency",
    "frequency_lcn_no": "Frequency",
    "frequency_no": "Frequency",
}


def normalize_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_frequency(value: Any) -> str | None:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        numeric = pd.to_numeric(value)
        if pd.isna(numeric):
            return None
        if float(numeric).is_integer():
            return str(int(numeric))
        return str(float(numeric))
    except Exception:
        return None


def parse_week_number(path: Path) -> int:
    match = re.search(r"week\D*(\d+)", path.stem, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    fallback = re.search(r"(\d+)", path.stem)
    return int(fallback.group(1)) if fallback else 9999


def week_column_name(index: int) -> str:
    return f"W{index}"


def format_week_label(path: Path) -> str:
    week_number = parse_week_number(path)
    year_suffix = infer_year_suffix_from_path(path)
    return f"Week{week_number:02d}'{year_suffix}"


def infer_year_suffix_from_path(path: Path) -> str:
    stem = path.stem
    four_digit = re.search(r"(20\d{2})", stem)
    if four_digit:
        return four_digit.group(1)[-2:]
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%y")


def build_week_label_map(files: list[Path]) -> dict[str, str]:
    label_map: dict[str, str] = {}
    for index, path in enumerate(files, start=1):
        label_map[week_column_name(index)] = format_week_label(path)
    return label_map


def scan_week_files(data_dir: Path) -> list[Path]:
    files = []
    for path in sorted(data_dir.glob("*.xls*")):
        if path.name.startswith("~$"):
            continue
        files.append(path)
    return sorted(files, key=parse_week_number)


def build_business_key(row: pd.Series) -> str:
    return "|".join(normalize_text(row[column]) for column in BUSINESS_KEY_COLUMNS)


def load_json_param(raw_value: str | None, default: Any) -> Any:
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return default


def ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def distinct_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    return sorted({normalize_text(value) for value in df[column].dropna().tolist() if normalize_text(value)})


def available_week_columns(df: pd.DataFrame) -> list[str]:
    return sorted(
        [column for column in df.columns if re.fullmatch(r"W\d+", column)],
        key=lambda item: int(item[1:]),
    )
