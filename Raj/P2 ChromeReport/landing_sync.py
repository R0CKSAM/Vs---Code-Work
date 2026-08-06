from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
LANDING_ANALYSIS_DIR = BASE_DIR / "landing analysis"
FALLBACK_LANDING_DIR = BASE_DIR / "landing"
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = BASE_DIR / "history"
OUTPUT_DIR = BASE_DIR / "output"
LANDING_HISTORY_CSV = HISTORY_DIR / "landing_history.csv"
LANDING_REPORT_JSON = OUTPUT_DIR / "landing_report.json"

REQUIRED_COLUMNS = [
    "Band",
    "Market",
    "City",
    "Headend",
    "State",
    "District",
    "Feed",
    "CRN NO",
    "SF CRN",
    "MSO",
    "PUT-UP LCN",
    "PUT-UP CHANNEL",
    "BARKER 1 LCN",
    "BARKER 1 CHANNEL",
    "BARKER 2 LCN",
    "BARKER 2 CHANNEL",
    "LANDING 1 LCN",
    "LANDING 1 CHANNEL",
    "LANDING 1 GENRE",
    "LANDING 2 LCN",
    "LANDING 2 CHANNEL",
    "LANDING 2 GENRE",
    "LANDING 3 LCN",
    "LANDING 3 CHANNEL",
    "LANDING 3 GENRE",
]

IGNORE_FILENAMES = {"temp.xlsx", "copy.xlsx", "notes.xlsx"}

WEEK_PATTERN = re.compile(r"Wk[-_]?\s*0*(?P<week>\d{1,2})(?:[,\s]*20(?P<year>\d{2}))?", re.IGNORECASE)
ALT_WEEK_PATTERN = re.compile(r"Week[-_]?\s*0*(?P<week>\d{1,2})", re.IGNORECASE)


def detect_week_label(filename: str) -> str:
    match = WEEK_PATTERN.search(filename)
    if match:
        week = int(match.group("week"))
        year = match.group("year") or "26"
        return f"Wk-{week:02d}'{year}"
    alt_match = ALT_WEEK_PATTERN.search(filename)
    if alt_match:
        week = int(alt_match.group("week"))
        return f"Wk-{week:02d}'26"
    return filename.replace(".xlsx", "")


def clean_str(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    text = str(val).strip()
    return "" if text.upper() in {"NAN", "NONE", "NULL"} else text


def parse_landing_file(file_path: Path) -> list[dict[str, Any]]:
    # Attempt reading with multi-level header (header=[0, 1]) first
    df_raw = pd.read_excel(file_path, header=None)

    # Detect if row 0 has Group Headers like BARKER 1, LANDING 1 etc.
    row0_str = " ".join([clean_str(x).upper() for x in df_raw.iloc[0].values])
    is_two_level = any(g in row0_str for g in ["BARKER 1", "BARKER 2", "LANDING 1", "LANDING 2", "LANDING 3"])

    if is_two_level:
        df = pd.read_excel(file_path, header=[0, 1])
        # Flatten MultiIndex columns
        flat_cols: list[str] = []
        current_group = ""
        for top, sub in df.columns:
            top_s = clean_str(top).upper()
            sub_s = clean_str(sub).upper()
            if top_s and not top_s.startswith("UNNAMED"):
                current_group = top_s

            if current_group in {"BARKER 1", "BARKER 2", "LANDING 1", "LANDING 2", "LANDING 3"}:
                col_name = f"{current_group} {sub_s}".strip()
            else:
                col_name = sub_s if sub_s and not sub_s.startswith("UNNAMED") else top_s
            flat_cols.append(col_name)
        df.columns = flat_cols
    else:
        df = pd.read_excel(file_path)

    # Normalize column mapping
    header_map: dict[str, str] = {}
    for col in df.columns:
        c_upper = clean_str(col).upper().replace("-", " ").replace(".", " ").replace("_", " ")
        c_upper = " ".join(c_upper.split())

        if c_upper in {"BAND"}:
            header_map["Band"] = col
        elif c_upper in {"MARKET"}:
            header_map["Market"] = col
        elif c_upper in {"CITY"}:
            header_map["City"] = col
        elif c_upper in {"HEAD END", "HEADEND"}:
            header_map["Headend"] = col
        elif c_upper in {"STATE"}:
            header_map["State"] = col
        elif c_upper in {"DISTRICT"}:
            header_map["District"] = col
        elif c_upper in {"FEED"}:
            header_map["Feed"] = col
        elif c_upper in {"CRN NO", "CRN", "CRN NUMBER"}:
            header_map["CRN NO"] = col
        elif c_upper in {"SF CRN", "SFRN NUMBER", "SFRN NO", "SF CRN NO"}:
            header_map["SF CRN"] = col
        elif c_upper in {"MSO", "MSO TYPE", "MSO NAME"}:
            header_map["MSO"] = col
        elif c_upper in {"PUT UP LCN", "POPUP LCN", "PUTUP LCN", "POP UP LCN"}:
            header_map["PUT-UP LCN"] = col
        elif c_upper in {"PUT UP CHANNEL", "POPUP CHANNEL", "PUTUP CHANNEL", "POP UP CHANNEL"}:
            header_map["PUT-UP CHANNEL"] = col
        elif c_upper in {"BARKER 1 LCN"}:
            header_map["BARKER 1 LCN"] = col
        elif c_upper in {"BARKER 1 CHANNEL", "BARKER 1"}:
            header_map["BARKER 1 CHANNEL"] = col
        elif c_upper in {"BARKER 2 LCN"}:
            header_map["BARKER 2 LCN"] = col
        elif c_upper in {"BARKER 2 CHANNEL", "BARKER 2"}:
            header_map["BARKER 2 CHANNEL"] = col
        elif c_upper in {"LANDING 1 LCN"}:
            header_map["LANDING 1 LCN"] = col
        elif c_upper in {"LANDING 1 CHANNEL", "LANDING 1"}:
            header_map["LANDING 1 CHANNEL"] = col
        elif c_upper in {"LANDING 1 GENRE"}:
            header_map["LANDING 1 GENRE"] = col
        elif c_upper in {"LANDING 2 LCN"}:
            header_map["LANDING 2 LCN"] = col
        elif c_upper in {"LANDING 2 CHANNEL", "LANDING 2"}:
            header_map["LANDING 2 CHANNEL"] = col
        elif c_upper in {"LANDING 2 GENRE"}:
            header_map["LANDING 2 GENRE"] = col
        elif c_upper in {"LANDING 3 LCN"}:
            header_map["LANDING 3 LCN"] = col
        elif c_upper in {"LANDING 3 CHANNEL", "LANDING 3"}:
            header_map["LANDING 3 CHANNEL"] = col
        elif c_upper in {"LANDING 3 GENRE"}:
            header_map["LANDING 3 GENRE"] = col

    week_label = detect_week_label(file_path.name)
    records: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        rec: dict[str, Any] = {
            "Week": week_label,
            "Band": clean_str(row.get(header_map.get("Band", ""))),
            "Market": clean_str(row.get(header_map.get("Market", ""))),
            "City": clean_str(row.get(header_map.get("City", ""))),
            "Headend": clean_str(row.get(header_map.get("Headend", ""))),
            "State": clean_str(row.get(header_map.get("State", ""))),
            "District": clean_str(row.get(header_map.get("District", ""))),
            "Feed": clean_str(row.get(header_map.get("Feed", ""))),
            "CRN NO": clean_str(row.get(header_map.get("CRN NO", ""))),
            "SF CRN": clean_str(row.get(header_map.get("SF CRN", ""))),
            "MSO": clean_str(row.get(header_map.get("MSO", ""))),
            "PUT-UP LCN": clean_str(row.get(header_map.get("PUT-UP LCN", ""))),
            "PUT-UP CHANNEL": clean_str(row.get(header_map.get("PUT-UP CHANNEL", ""))),
            "Barker 1 LCN": clean_str(row.get(header_map.get("BARKER 1 LCN", ""))),
            "Barker 1 Channel": clean_str(row.get(header_map.get("BARKER 1 CHANNEL", ""))),
            "Barker 2 LCN": clean_str(row.get(header_map.get("BARKER 2 LCN", ""))),
            "Barker 2 Channel": clean_str(row.get(header_map.get("BARKER 2 CHANNEL", ""))),
            "Landing 1 LCN": clean_str(row.get(header_map.get("LANDING 1 LCN", ""))),
            "Landing 1 Channel": clean_str(row.get(header_map.get("LANDING 1 CHANNEL", ""))),
            "Landing 1 Genre": clean_str(row.get(header_map.get("LANDING 1 GENRE", ""))),
            "Landing 2 LCN": clean_str(row.get(header_map.get("LANDING 2 LCN", ""))),
            "Landing 2 Channel": clean_str(row.get(header_map.get("LANDING 2 CHANNEL", ""))),
            "Landing 2 Genre": clean_str(row.get(header_map.get("LANDING 2 GENRE", ""))),
            "Landing 3 LCN": clean_str(row.get(header_map.get("LANDING 3 LCN", ""))),
            "Landing 3 Channel": clean_str(row.get(header_map.get("LANDING 3 CHANNEL", ""))),
            "Landing 3 Genre": clean_str(row.get(header_map.get("LANDING 3 GENRE", ""))),
        }
        records.append(rec)

    return records


def get_landing_files() -> list[Path]:
    files: list[Path] = []
    dirs = [LANDING_ANALYSIS_DIR, FALLBACK_LANDING_DIR]
    seen_names: set[str] = set()

    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.xlsx")):
            if p.name.startswith("~$") or p.name.lower() in IGNORE_FILENAMES:
                continue
            if p.name not in seen_names:
                seen_names.add(p.name)
                files.append(p)

    return files


def sync_landing_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LANDING_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    files = get_landing_files()
    if not files:
        print("No Excel files found in 'landing analysis/' folder.")
        return

    existing_df = pd.DataFrame()
    if LANDING_HISTORY_CSV.exists():
        try:
            existing_df = pd.read_csv(LANDING_HISTORY_CSV, dtype=str)
        except Exception:
            existing_df = pd.DataFrame()

    all_records: list[dict[str, Any]] = existing_df.to_dict("records") if not existing_df.empty else []

    for file_path in files:
        print(f"\nReading {file_path.name}")
        try:
            records = parse_landing_file(file_path)
            week_label = detect_week_label(file_path.name)
            all_records = [r for r in all_records if r.get("Week") != week_label]
            all_records.extend(records)
            print(f"✓ {len(records):,} rows imported")
        except Exception as err:
            print(f"✗ Error reading {file_path.name}: {err}")

    if all_records:
        df_out = pd.DataFrame(all_records)
        df_out.to_csv(LANDING_HISTORY_CSV, index=False)
        try:
            from app import load_report, write_frequency_report_json, write_standalone_dashboard
            report = load_report(force=True)
            write_frequency_report_json(report)
            write_standalone_dashboard(report)
        except Exception:
            pass
        print("\nDashboard Updated Successfully.")


if __name__ == "__main__":
    sync_landing_data()
