from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
LANDING_DIR = BASE_DIR / "landing"
FALLBACK_LANDING_DIR = BASE_DIR / "landing analysis"
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = BASE_DIR / "history"
OUTPUT_DIR = BASE_DIR / "output"

LANDING_HISTORY_CSV = HISTORY_DIR / "landing_history.csv"
PROCESSED_LOG_JSON = DATA_DIR / "processed_landing_files.json"

WEEK_PATTERN = re.compile(r"Wk[-_]?\s*0*(?P<week>\d{1,2})(?:[,\s]*20(?P<year>\d{2}))?", re.IGNORECASE)
ALT_WEEK_PATTERN = re.compile(r"Week[-_]?\s*0*(?P<week>\d{1,2})", re.IGNORECASE)

IGNORE_FILENAMES = {"temp.xlsx", "copy.xlsx", "notes.xlsx"}


def extract_week_name(filename: str) -> str:
    """Extract week label from filename, e.g. 'Wk-30' or 'Week 30'."""
    match = WEEK_PATTERN.search(filename)
    if match:
        week_num = int(match.group("week"))
        return f"Week {week_num}"
    alt_match = ALT_WEEK_PATTERN.search(filename)
    if alt_match:
        week_num = int(alt_match.group("week"))
        return f"Week {week_num}"
    return filename.replace(".xlsx", "")


def clean_str(val: Any) -> str:
    """Normalize string and strip empty/NaN values."""
    if val is None or pd.isna(val):
        return ""
    text = str(val).strip()
    return "" if text.upper() in {"NAN", "NONE", "NULL"} else text


def parse_landing_excel(file_path: Path) -> list[dict[str, Any]]:
    """Automatically detect columns, handle single and multi-level headers, and normalize data."""
    df_raw = pd.read_excel(file_path, header=None)
    if df_raw.empty:
        return []

    header_idx = 0
    for idx, row in df_raw.iterrows():
        row_str = " ".join([clean_str(x).upper() for x in row.values])
        if any(k in row_str for k in ["MARKET", "CITY", "HEADEND", "HEAD END", "CRN"]):
            header_idx = idx
            break

    is_two_level = False
    if header_idx + 1 < len(df_raw):
        r0_str = " ".join([clean_str(x).upper() for x in df_raw.iloc[header_idx].values])
        r1_str = " ".join([clean_str(x).upper() for x in df_raw.iloc[header_idx + 1].values])
        if any(g in r0_str for g in ["BARKER 1", "BARKER 2", "LANDING 1", "LANDING 2", "LANDING 3"]) and any(s in r1_str for s in ["LCN", "CHANNEL", "GENRE"]):
            is_two_level = True

    if is_two_level:
        df = pd.read_excel(file_path, header=[header_idx, header_idx + 1])
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
        df.columns = pd.Index(flat_cols)
    else:
        df = pd.read_excel(file_path, header=header_idx)
        df.columns = pd.Index([clean_str(c) for c in df.columns])

    header_map: dict[str, str] = {}
    for col in df.columns:
        c_upper = clean_str(col).upper().replace("-", " ").replace(".", " ").replace("_", " ")
        c_upper = " ".join(c_upper.split())

        if "BAND" in c_upper:
            header_map["Band"] = col
        elif "MARKET" in c_upper:
            header_map["Market"] = col
        elif "CITY" in c_upper:
            header_map["City"] = col
        elif "HEADEND" in c_upper or "HEAD END" in c_upper:
            header_map["Headend"] = col
        elif "STATE" in c_upper:
            header_map["State"] = col
        elif "DISTRICT" in c_upper:
            header_map["District"] = col
        elif "FEED" in c_upper:
            header_map["Feed"] = col
        elif "SF" in c_upper and ("CRN" in c_upper or "SFRN" in c_upper):
            header_map["SF CRN"] = col
        elif "CRN" in c_upper:
            header_map["CRN NO"] = col
        elif "MSO" in c_upper:
            header_map["MSO"] = col
        elif "PUT" in c_upper and "LCN" in c_upper:
            header_map["PUT-UP LCN"] = col
        elif "PUT" in c_upper and "CHANNEL" in c_upper:
            header_map["PUT-UP CHANNEL"] = col
        elif "BARKER 1" in c_upper and "LCN" in c_upper:
            header_map["BARKER 1 LCN"] = col
        elif "BARKER 1" in c_upper and ("CHANNEL" in c_upper or c_upper.endswith("BARKER 1")):
            header_map["BARKER 1 CHANNEL"] = col
        elif "BARKER 2" in c_upper and "LCN" in c_upper:
            header_map["BARKER 2 LCN"] = col
        elif "BARKER 2" in c_upper and ("CHANNEL" in c_upper or c_upper.endswith("BARKER 2")):
            header_map["BARKER 2 CHANNEL"] = col
        elif "LANDING 1" in c_upper and "LCN" in c_upper:
            header_map["LANDING 1 LCN"] = col
        elif "LANDING 1" in c_upper and "GENRE" in c_upper:
            header_map["LANDING 1 GENRE"] = col
        elif "LANDING 1" in c_upper and ("CHANNEL" in c_upper or c_upper.endswith("LANDING 1")):
            header_map["LANDING 1 CHANNEL"] = col
        elif "LANDING 2" in c_upper and "LCN" in c_upper:
            header_map["LANDING 2 LCN"] = col
        elif "LANDING 2" in c_upper and "GENRE" in c_upper:
            header_map["LANDING 2 GENRE"] = col
        elif "LANDING 2" in c_upper and ("CHANNEL" in c_upper or c_upper.endswith("LANDING 2")):
            header_map["LANDING 2 CHANNEL"] = col
        elif "LANDING 3" in c_upper and "LCN" in c_upper:
            header_map["LANDING 3 LCN"] = col
        elif "LANDING 3" in c_upper and "GENRE" in c_upper:
            header_map["LANDING 3 GENRE"] = col
        elif "LANDING 3" in c_upper and ("CHANNEL" in c_upper or c_upper.endswith("LANDING 3")):
            header_map["LANDING 3 CHANNEL"] = col

    week_name = extract_week_name(file_path.name)
    records: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        rec: dict[str, Any] = {
            "Week": week_name,
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
            "Landing 1 LCN": clean_str(row.get(header_map.get("LANDING 1 LCN", ""))) or clean_str(row.get(header_map.get("PUT-UP LCN", ""))),
            "Landing 1 Channel": clean_str(row.get(header_map.get("LANDING 1 CHANNEL", ""))) or clean_str(row.get(header_map.get("PUT-UP CHANNEL", ""))),
            "Landing 1 Genre": clean_str(row.get(header_map.get("LANDING 1 GENRE", ""))),
            "Landing 2 LCN": clean_str(row.get(header_map.get("LANDING 2 LCN", ""))),
            "Landing 2 Channel": clean_str(row.get(header_map.get("LANDING 2 CHANNEL", ""))),
            "Landing 2 Genre": clean_str(row.get(header_map.get("LANDING 2 GENRE", ""))),
            "Landing 3 LCN": clean_str(row.get(header_map.get("LANDING 3 LCN", ""))),
            "Landing 3 Channel": clean_str(row.get(header_map.get("LANDING 3 CHANNEL", ""))),
            "Landing 3 Genre": clean_str(row.get(header_map.get("LANDING 3 GENRE", ""))),
        }
        # Only add valid rows that have at least Market or Headend or Landing Channel
        if rec["Market"] or rec["Headend"] or rec["Landing 1 Channel"] or rec["City"]:
            records.append(rec)

    return records


def load_processed_files_log() -> set[str]:
    """Load history of processed files."""
    if PROCESSED_LOG_JSON.exists():
        try:
            data = json.loads(PROCESSED_LOG_JSON.read_text(encoding="utf-8"))
            return set(data.get("processed_files", []))
        except Exception:
            return set()
    return set()


def save_processed_files_log(processed: set[str]) -> None:
    """Save history of processed files."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "processed_files": sorted(list(processed))}
    PROCESSED_LOG_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_landing_files() -> list[Path]:
    """Scan landing/ and landing analysis/ directories for Excel files."""
    files: list[Path] = []
    dirs = [LANDING_DIR, FALLBACK_LANDING_DIR]
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


def process_landing_tracker_files(force_reprocess: bool = False) -> dict[str, Any]:
    """Scan, parse files, update history, and return summary."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LANDING_DIR.mkdir(parents=True, exist_ok=True)

    processed_log = load_processed_files_log()
    candidate_files = get_landing_files()

    if force_reprocess:
        processed_log.clear()

    existing_df = pd.DataFrame()
    if LANDING_HISTORY_CSV.exists() and not force_reprocess:
        try:
            existing_df = pd.read_csv(LANDING_HISTORY_CSV, dtype=str)
        except Exception:
            existing_df = pd.DataFrame()

    all_records: list[dict[str, Any]] = existing_df.to_dict("records") if not existing_df.empty else []

    processed_count = 0
    for file_path in candidate_files:
        if file_path.name in processed_log and not existing_df.empty and not force_reprocess:
            continue

        print(f"Processing landing file: {file_path.name}")
        try:
            records = parse_landing_excel(file_path)
            week_label = extract_week_name(file_path.name)
            all_records = [r for r in all_records if r.get("Week") != week_label]
            all_records.extend(records)
            processed_log.add(file_path.name)
            processed_count += 1
            print(f"  ✓ {len(records):,} records imported for {week_label}")
        except Exception as err:
            print(f"  ✗ Error reading {file_path.name}: {err}")

    if all_records:
        df_out = pd.DataFrame(all_records)
        df_out.to_csv(LANDING_HISTORY_CSV, index=False)
        save_processed_files_log(processed_log)

    return {
        "processed": processed_count,
        "skipped": len(candidate_files) - processed_count,
        "total_records": len(all_records),
    }


if __name__ == "__main__":
    res = process_landing_tracker_files(force_reprocess=True)
    print(json.dumps(res, indent=2))
