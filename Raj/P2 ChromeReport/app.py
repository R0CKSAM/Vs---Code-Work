from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook, load_workbook
from weekly_workbook_builder import ensure_combined_weekly_workbooks


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DISTRIBUTION_SUMMARY_DIR = BASE_DIR / "distribution summary"
NBHD_DATA_DIR = BASE_DIR / "NBHD Data"
LEGACY_NBHD_DATA_DIR = BASE_DIR / "NBHD"
OTS_DATA_DIR = BASE_DIR / "OTS"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_JSON = OUTPUT_DIR / "frequency_report.json"
OUTPUT_HTML = OUTPUT_DIR / "chrome_report_dashboard.html"
HISTORY_DIR = BASE_DIR / "history"
HISTORY_DISTRIBUTION_CSV = HISTORY_DIR / "distribution_history.csv"
HISTORY_NBHD_CSV = HISTORY_DIR / "nbhd_history.csv"
HISTORY_OTS_CSV = HISTORY_DIR / "ots_history.csv"
LEGACY_HISTORY_DISTRIBUTION_CSV = BASE_DIR / "distribution_history.csv"
LEGACY_HISTORY_NBHD_CSV = BASE_DIR / "nbhd_history.csv"
LEGACY_HISTORY_OTS_CSV = BASE_DIR / "ots_history.csv"
STYLE_FILE = BASE_DIR / "static" / "style.css"
NBHD_SCRIPT_FILE = BASE_DIR / "static" / "neighbourhood.js"
OTS_SCRIPT_FILE = BASE_DIR / "static" / "ots.js"
COMPARISON_SCRIPT_FILE = BASE_DIR / "static" / "comparison.js"
NBHD_WEEKWISE_SCRIPT_FILE = BASE_DIR / "static" / "nbhd_weekwise.js"
NBHD_BENCHMARK_SCRIPT_FILE = BASE_DIR / "static" / "nbhd_benchmark.js"
LANDING_SCRIPT_FILE = BASE_DIR / "static" / "landing.js"
LANDING_ANALYSIS_DIR = BASE_DIR / "landing analysis"
LANDING_HISTORY_CSV = HISTORY_DIR / "landing_history.csv"

SOURCE_COLUMNS = [
    "WEEK LABEL",
    "TRANSMISSION",
    "MARKET",
    "GENRE",
    "MSO TYPE",
    "CITY",
    "HEAD-END",
    "CHANNEL NAME",
    "FREQUENCY/LCN NO",
    "BAND",
    "TV CH. No.",
    "AUDIO",
    "VIDEO",
    "LANGUAGE",
    "CRN No.",
    "RANK WITHIN GENRE",
]
KEY_COLUMNS = [
    "TRANSMISSION",
    "MARKET",
    "MSO TYPE",
    "CITY",
    "HEAD-END",
    "CHANNEL NAME",
    "CRN No.",
]
DISPLAY_COLUMNS = [
    "TRANSMISSION",
    "MARKET",
    "MSO TYPE",
    "CITY",
    "HEAD-END",
    "CHANNEL NAME",
    "WEEK LABEL",
    "GENRE",
    "LANGUAGE",
    "NAME",
]
FREQUENCY_COLUMN = "FREQUENCY/LCN NO"
RANK_COLUMN = "RANK WITHIN GENRE"

FOCUS_CHANNELS = {
    "INDIA TV": "India TV",
    "AAJ TAK": "Aaj Tak",
    "NEWS 18 INDIA": "News 18",
    "REPUBLIC BHARAT": "Republic Bharat",
}

REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}
NBHD_REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}
OTS_REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}
COMPARISON_REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}
NBHD_BENCHMARK_REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}
NBHD_WEEKWISE_REPORT_CACHE: dict[str, Any] = {
    "signature": None,
    "report": None,
}


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    NBHD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def sort_summary_channels(channels: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        label = normalize_text(channel)
        if not label:
            continue
        normalized = label.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(label)
    return [channel for channel in ordered if normalize_text(channel).upper() == "INDIA TV"] + sorted(
        [channel for channel in ordered if normalize_text(channel).upper() != "INDIA TV"],
        key=lambda channel: normalize_text(channel).upper(),
    )


def normalize_number(value: Any) -> float | int | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    return int(number) if number.is_integer() else number


def normalize_rank(value: Any) -> int | None:
    number = normalize_number(value)
    if number is None:
        return None
    return int(number)


def week_sort_key(label: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", label)
    if match:
        return int(match.group(1)), label
    return 10**9, label


def parse_workbook_week(path: Path) -> tuple[int, int] | None:
    match = re.search(r"wk[-\s_]*(\d{1,2}).*?(20\d{2})", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(2)), int(match.group(1))
    match = re.search(r"(20\d{2}).*?wk[-\s_]*(\d{1,2})", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def format_week_label(week_number: int, year: int) -> str:
    return f"Wk-{int(week_number):02d}'{str(year)[-2:]}"


def get_signature(files: list[Path]) -> tuple[tuple[str, int, int], ...]:
    return tuple((path.name, int(path.stat().st_mtime), path.stat().st_size) for path in files)


def history_files_ready() -> bool:
    paths = [resolve_history_path(HISTORY_DISTRIBUTION_CSV, LEGACY_HISTORY_DISTRIBUTION_CSV), resolve_history_path(HISTORY_NBHD_CSV, LEGACY_HISTORY_NBHD_CSV), resolve_history_path(HISTORY_OTS_CSV, LEGACY_HISTORY_OTS_CSV)]
    return all(path.exists() and path.stat().st_size > 0 for path in paths)


def get_history_signature() -> tuple[tuple[str, int, int], ...]:
    paths = [
        path
        for path in [
            resolve_history_path(HISTORY_DISTRIBUTION_CSV, LEGACY_HISTORY_DISTRIBUTION_CSV),
            resolve_history_path(HISTORY_NBHD_CSV, LEGACY_HISTORY_NBHD_CSV),
            resolve_history_path(HISTORY_OTS_CSV, LEGACY_HISTORY_OTS_CSV),
        ]
        if path.exists()
    ]
    return get_signature(paths)


def read_history_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False)


def resolve_history_path(primary: Path, legacy: Path) -> Path:
    if primary.exists():
        return primary
    return legacy


def normalize_header_key(value: Any) -> str:
    text = normalize_text(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def get_nbhd_input_dir() -> Path:
    ensure_directories()
    primary_files = list(NBHD_DATA_DIR.glob("*.xlsx"))
    if primary_files:
        return NBHD_DATA_DIR
    return LEGACY_NBHD_DATA_DIR if LEGACY_NBHD_DATA_DIR.exists() else NBHD_DATA_DIR


def get_nbhd_source_dir() -> Path:
    ensure_directories()
    nbhd_input_dir = get_nbhd_input_dir()
    input_files = [path for path in nbhd_input_dir.glob("*.xlsx") if not path.name.startswith("~$")]
    if input_files:
        return nbhd_input_dir
    combined_files = [path for path in DATA_DIR.glob("*.xlsx") if not path.name.startswith("~$")]
    if combined_files:
        return DATA_DIR
    return nbhd_input_dir


def get_ots_input_dir() -> Path:
    ensure_directories()
    return OTS_DATA_DIR


def get_ots_source_dir() -> Path:
    ensure_directories()
    ots_input_dir = get_ots_input_dir()
    input_files = [path for path in ots_input_dir.glob("*.xlsx") if not path.name.startswith("~$")]
    if input_files:
        return ots_input_dir
    combined_files = [path for path in DATA_DIR.glob("*.xlsx") if not path.name.startswith("~$")]
    if combined_files:
        return DATA_DIR
    return ots_input_dir


def get_week_files() -> list[Path]:
    ensure_directories()
    ensure_combined_weekly_workbooks(DATA_DIR, DISTRIBUTION_SUMMARY_DIR, get_nbhd_input_dir(), get_ots_input_dir())
    xlsx_files = [path for path in DATA_DIR.glob("*.xlsx") if not path.name.startswith("~$")]
    xlsm_files = [path for path in DATA_DIR.glob("*.xlsm") if not path.name.startswith("~$")]
    if xlsx_files and len(xlsx_files) >= len(xlsm_files):
        return sorted(xlsx_files, key=lambda path: week_sort_key(path.stem))
    if xlsm_files:
        return sorted(xlsm_files, key=lambda path: week_sort_key(path.stem))
    return sorted(xlsx_files, key=lambda path: week_sort_key(path.stem))


def get_nbhd_week_files() -> list[Path]:
    source_dir = get_nbhd_source_dir()
    files = [path for path in source_dir.glob("*.xlsx") if not path.name.startswith("~$")]
    return sorted(files, key=lambda path: week_sort_key(path.stem))


def get_ots_week_files() -> list[Path]:
    ensure_directories()
    files = [path for path in get_ots_source_dir().glob("*.xlsx") if not path.name.startswith("~$")]
    return sorted(files, key=lambda path: week_sort_key(path.stem))


def get_highlight_week_files() -> list[Path]:
    ensure_directories()
    files = [
        path
        for pattern in ("*.xlsm", "*.xlsx")
        for path in DATA_DIR.glob(pattern)
        if not path.name.startswith("~$")
    ]
    return sorted(
        {path.resolve(): path for path in files}.values(),
        key=lambda path: parse_workbook_week(path) or (10**9, 10**9),
    )


def empty_nbhd_report(message: str | None = None) -> dict[str, Any]:
    source_dir = get_nbhd_source_dir()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": [],
        "records": [],
        "message": message or "Add weekly neighbourhood Excel files to the NBHD Data folder.",
        "source_directory": str(source_dir),
    }


def empty_ots_report(message: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": [],
        "records": [],
        "message": message or "Add weekly OTS Excel files to the data folder.",
        "source_directory": str(get_ots_source_dir()),
    }


def prepare_nbhd_week_rows(path: Path) -> tuple[str, list[dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["NBDH Data"] if "NBDH Data" in workbook.sheetnames else workbook[workbook.sheetnames[0]]

    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    header_map = {normalize_header_key(value): index for index, value in enumerate(header_row)}

    field_aliases = {
        "type": ("TYPE",),
        "frequency": ("FREQU", "FREQUENCY"),
        "tv_ch_no": ("TVCHANNELNO", "TVCHNO"),
        "market": ("MARKET",),
        "city": ("CITY",),
        "head_end": ("HEADEND",),
        "channel": ("CHANNEL",),
        "genre": ("GENRE",),
    }

    field_indexes: dict[str, int] = {}
    missing_fields: list[str] = []
    for field, aliases in field_aliases.items():
        index = next((header_map[alias] for alias in aliases if alias in header_map), None)
        if index is None:
            missing_fields.append(field)
        else:
            field_indexes[field] = index

    if missing_fields:
        workbook.close()
        raise ValueError(f"{path.name} is missing required columns: {', '.join(missing_fields)}")

    week_label = normalize_text(path.stem).upper()
    rows: list[dict[str, Any]] = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        row = {
            field: values[index] if index < len(values) else None
            for field, index in field_indexes.items()
        }
        market = normalize_text(row["market"])
        city = normalize_text(row["city"])
        head_end = normalize_text(row["head_end"])
        channel = normalize_text(row["channel"])
        if not market or not city or not head_end or not channel:
            continue
        rows.append(
            {
                "type": normalize_text(row["type"]),
                "market": market,
                "city": city,
                "head_end": head_end,
                "channel": channel,
                "genre": normalize_text(row["genre"]),
                "frequency": normalize_number(row["frequency"]),
                "tv_ch_no": normalize_number(row["tv_ch_no"]),
                "order_token": normalize_number(row["tv_ch_no"]) if normalize_number(row["tv_ch_no"]) is not None else normalize_number(row["frequency"]),
            }
        )

    workbook.close()
    return week_label, rows


def normalize_ots_percentage(value: Any) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    number = normalize_number(value)
    if number is None:
        return None
    normalized = float(number)
    if "%" not in text and abs(normalized) <= 1:
        normalized *= 100
    return round(normalized, 2)


def prepare_ots_week_rows(path: Path) -> tuple[str, list[dict[str, Any]]]:
    # Read one normalized weekly OTS workbook into market/channel/value rows.
    workbook = load_workbook(path, read_only=True, data_only=True)
    if "OTS Data" in workbook.sheetnames:
        sheet_name = "OTS Data"
    elif "Table1" in workbook.sheetnames:
        sheet_name = "Table1"
    else:
        sheet_name = workbook.sheetnames[0]
    sheet = workbook[sheet_name]

    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    header_map = {normalize_header_key(value): index for index, value in enumerate(header_row)}

    required_headers = {
        "market": ("MARKET",),
        "channel": ("CHANNEL", "ATTRIBUTE"),
        "ots": ("OTS", "VALUE"),
    }
    field_indexes: dict[str, int] = {}
    missing_fields: list[str] = []
    for field, aliases in required_headers.items():
        index = next((header_map[alias] for alias in aliases if alias in header_map), None)
        if index is None:
            missing_fields.append(field)
        else:
            field_indexes[field] = index

    if missing_fields:
        workbook.close()
        raise ValueError(f"{path.name} is missing required columns: {', '.join(missing_fields)}")

    week_index = next((header_map[alias] for alias in ("WEEK",) if alias in header_map), None)

    week_label = normalize_text(path.stem)
    rows: list[dict[str, Any]] = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        market = normalize_text(values[field_indexes["market"]] if field_indexes["market"] < len(values) else None)
        channel = normalize_text(values[field_indexes["channel"]] if field_indexes["channel"] < len(values) else None)
        ots_value = normalize_ots_percentage(values[field_indexes["ots"]] if field_indexes["ots"] < len(values) else None)
        if not market or not channel:
            continue
        week_value = normalize_text(values[week_index] if week_index is not None and week_index < len(values) else None)
        if week_value:
            week_label = week_value.replace("Week", "Week ").replace("week", "Week ").replace("  ", " ").strip()

        rows.append(
            {
                "market": market,
                "channel": channel,
                "ots": ots_value,
            }
        )

    workbook.close()

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(f"{row['market']}||{row['channel']}", row)
    return week_label, list(deduped.values())


def get_nbhd_sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed_rows = list(enumerate(rows))
    indexed_rows.sort(
        key=lambda item: (
            item[1].get("order_token") is None,
            item[1].get("order_token") if item[1].get("order_token") is not None else item[0],
            item[0],
        )
    )
    return [row for _, row in indexed_rows]


def extract_nbhd_window(rows: list[dict[str, Any]], radius: int = 4) -> list[tuple[int, dict[str, Any]]]:
    sorted_rows = get_nbhd_sorted_rows(rows)
    focus_channel_keys = set(FOCUS_CHANNELS)
    focus_indexes = [
        index
        for index, row in enumerate(sorted_rows)
        if normalize_text(row["channel"]).upper() in focus_channel_keys
    ]
    if not focus_indexes:
        return []

    window_indexes: set[int] = set()
    for focus_index in focus_indexes:
        for offset in range(-radius, radius + 1):
            row_index = focus_index + offset
            if 0 <= row_index < len(sorted_rows):
                window_indexes.add(row_index)

    return [(row_index + 1, sorted_rows[row_index]) for row_index in sorted(window_indexes)]


def enumerate_nbhd_positions(rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    sorted_rows = get_nbhd_sorted_rows(rows)
    return [(row_index + 1, row) for row_index, row in enumerate(sorted_rows)]


def build_nbhd_channel_rows(group_rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    return enumerate_nbhd_positions(group_rows)


NBHD_WEEKWISE_COLUMNS = [
    "week",
    "market",
    "city",
    "head_end",
    "c1",
    "c2",
    "c3",
    "c4",
    "c5",
    "c6",
    "c7",
    "c8",
    "c9",
    "genre1",
    "genre2",
    "genre3",
    "genre4",
    "genre5",
    "genre6",
    "genre7",
    "genre8",
    "genre9",
]

NBHD_WEEKWISE_COLUMN_LABELS = {
    "week": "Week No",
    "market": "Market",
    "city": "City",
    "head_end": "Headend",
    "c1": "C-1",
    "c2": "C-2",
    "c3": "C-3",
    "c4": "C-4",
    "c5": "C-5 (INDIA TV)",
    "c6": "C-6",
    "c7": "C-7",
    "c8": "C-8",
    "c9": "C-9",
    "genre1": "Genre 1",
    "genre2": "Genre 2",
    "genre3": "Genre 3",
    "genre4": "Genre 4",
    "genre5": "Genre 5",
    "genre6": "Genre 6",
    "genre7": "Genre 7",
    "genre8": "Genre 8",
    "genre9": "Genre 9",
}


def build_nbhd_weekwise_row(
    week_label: str,
    market: str,
    city: str,
    head_end: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_rows = get_nbhd_sorted_rows(rows)
    india_index = next(
        (index for index, row in enumerate(sorted_rows) if normalize_text(row.get("channel")).upper() == "INDIA TV"),
        None,
    )

    output = {
        "row_key": "||".join((week_label, market, city, head_end)),
        "week": week_label,
        "market": market,
        "city": city,
        "head_end": head_end,
    }
    for slot in range(1, 10):
        output[f"c{slot}"] = ""
        output[f"genre{slot}"] = ""

    if india_index is not None:
        slot_map = {
            0: 5,
            -4: 1,
            -3: 2,
            -2: 3,
            -1: 4,
            1: 6,
            2: 7,
            3: 8,
            4: 9,
        }
        for relative_index, slot in slot_map.items():
            source_index = india_index + relative_index
            if source_index < 0 or source_index >= len(sorted_rows):
                continue
            row = sorted_rows[source_index]
            output[f"c{slot}"] = normalize_text(row.get("channel"))
            output[f"genre{slot}"] = normalize_text(row.get("genre"))
        return output

    sequential_slots = [1, 2, 3, 4, 6, 7, 8, 9]
    for source_index, slot in enumerate(sequential_slots):
        if source_index >= len(sorted_rows):
            break
        row = sorted_rows[source_index]
        output[f"c{slot}"] = normalize_text(row.get("channel"))
        output[f"genre{slot}"] = normalize_text(row.get("genre"))
    return output


def build_nbhd_weekwise_report() -> dict[str, Any]:
    if history_files_ready():
        history_path = resolve_history_path(HISTORY_NBHD_CSV, LEGACY_HISTORY_NBHD_CSV)
        dataframe = read_history_csv(history_path)
        if dataframe.empty:
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "weeks": [],
                "columns": NBHD_WEEKWISE_COLUMNS,
                "column_labels": NBHD_WEEKWISE_COLUMN_LABELS,
                "records": [],
                "message": "NBHD history CSV is empty.",
                "source_directory": str(history_path),
            }

        grouped_rows: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in dataframe.to_dict(orient="records"):
            week_label = normalize_text(row.get("Week"))
            market = normalize_text(row.get("Market"))
            city = normalize_text(row.get("City"))
            head_end = normalize_text(row.get("Head-End"))
            channel = normalize_text(row.get("Channel"))
            if not week_label or not market or not city or not head_end or not channel:
                continue
            tv_ch_no = normalize_number(row.get("TV CH. No."))
            frequency = normalize_number(row.get("Frequency"))
            grouped_rows.setdefault((week_label, market, city, head_end), []).append(
                {
                    "market": market,
                    "city": city,
                    "head_end": head_end,
                    "channel": channel,
                    "genre": normalize_text(row.get("Genre")),
                    "frequency": frequency,
                    "tv_ch_no": tv_ch_no,
                    "order_token": tv_ch_no if tv_ch_no is not None else frequency,
                }
            )

        records = [
            build_nbhd_weekwise_row(week_label, market, city, head_end, rows)
            for (week_label, market, city, head_end), rows in grouped_rows.items()
        ]
        weeks = sorted({record["week"] for record in records}, key=week_sort_key)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "columns": NBHD_WEEKWISE_COLUMNS,
            "column_labels": NBHD_WEEKWISE_COLUMN_LABELS,
            "records": sorted(
                records,
                key=lambda item: (
                    week_sort_key(item["week"]),
                    item["market"].lower(),
                    item["city"].lower(),
                    item["head_end"].lower(),
                ),
            ),
            "message": "",
            "source_directory": str(history_path),
        }

    week_files = get_nbhd_week_files()
    if not week_files:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": [],
            "columns": NBHD_WEEKWISE_COLUMNS,
            "column_labels": NBHD_WEEKWISE_COLUMN_LABELS,
            "records": [],
            "message": "Add weekly NBHD files to generate the week-wise neighbourhood comparison report.",
            "source_directory": str(get_nbhd_source_dir()),
        }

    grouped_rows: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for week_label, rows in [prepare_nbhd_week_rows(path) for path in week_files]:
        for row in rows:
            key = (week_label, row["market"], row["city"], row["head_end"])
            grouped_rows.setdefault(key, []).append(row)

    records = [
        build_nbhd_weekwise_row(week_label, market, city, head_end, rows)
        for (week_label, market, city, head_end), rows in grouped_rows.items()
    ]
    weeks = sorted({record["week"] for record in records}, key=week_sort_key)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "columns": NBHD_WEEKWISE_COLUMNS,
        "column_labels": NBHD_WEEKWISE_COLUMN_LABELS,
        "records": sorted(
            records,
            key=lambda item: (
                week_sort_key(item["week"]),
                item["market"].lower(),
                item["city"].lower(),
                item["head_end"].lower(),
            ),
        ),
        "message": "",
        "source_directory": str(get_nbhd_source_dir()),
    }


def load_nbhd_weekwise_report(force: bool = False) -> dict[str, Any]:
    signature = get_history_signature() if history_files_ready() else get_signature(get_nbhd_week_files())
    if not force and NBHD_WEEKWISE_REPORT_CACHE["report"] is not None and NBHD_WEEKWISE_REPORT_CACHE["signature"] == signature:
        return NBHD_WEEKWISE_REPORT_CACHE["report"]

    report = build_nbhd_weekwise_report()
    NBHD_WEEKWISE_REPORT_CACHE["signature"] = signature
    NBHD_WEEKWISE_REPORT_CACHE["report"] = report
    return report


def build_nbhd_report() -> dict[str, Any]:
    if history_files_ready():
        history_path = resolve_history_path(HISTORY_NBHD_CSV, LEGACY_HISTORY_NBHD_CSV)
        dataframe = read_history_csv(history_path)
        if dataframe.empty:
            return empty_nbhd_report()

        weeks = sorted(dataframe["Week"].dropna().astype(str).unique().tolist(), key=week_sort_key)
        merged: dict[str, dict[str, Any]] = {}

        for week_label in weeks:
            week_frame = dataframe[dataframe["Week"].astype(str) == week_label].copy()
            rows = []
            for row in week_frame.to_dict(orient="records"):
                market = normalize_text(row.get("Market"))
                city = normalize_text(row.get("City"))
                head_end = normalize_text(row.get("Head-End"))
                channel = normalize_text(row.get("Channel"))
                if not market or not city or not head_end or not channel:
                    continue
                tv_ch_no = normalize_number(row.get("TV CH. No."))
                frequency = normalize_number(row.get("Frequency"))
                rows.append(
                    {
                        "type": normalize_text(row.get("Type")),
                        "market": market,
                        "city": city,
                        "head_end": head_end,
                        "channel": channel,
                        "genre": normalize_text(row.get("Genre")),
                        "frequency": frequency,
                        "tv_ch_no": tv_ch_no,
                        "order_token": tv_ch_no if tv_ch_no is not None else frequency,
                    }
                )

            grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault((row["market"], row["city"], row["head_end"]), []).append(row)

            for (market, city, head_end), group_rows in grouped.items():
                for offset, nbhd_row in build_nbhd_channel_rows(group_rows):
                    channel = normalize_text(nbhd_row["channel"])
                    row_key = comparison_record_key(market, city, head_end, channel)
                    record = merged.setdefault(
                        row_key,
                        {
                            "row_key": row_key,
                            "market": market,
                            "city": city,
                            "head_end": head_end,
                            "channel_name": channel,
                            "position": offset,
                            "positions": {},
                            "is_reference": False,
                            "channels": {},
                            "genres": {},
                            "frequencies": {},
                        },
                    )
                    if not normalize_text(record.get("channel_name")):
                        record["channel_name"] = channel
                    record["position"] = offset
                    record["positions"][week_label] = offset
                    record["channels"][week_label] = channel
                    record["genres"][week_label] = normalize_text(nbhd_row["genre"])
                    record["frequencies"][week_label] = nbhd_row["frequency"]
                    if channel.upper() in FOCUS_CHANNELS:
                        record["is_reference"] = True

        records = list(merged.values())
        for record in records:
            for week in weeks:
                record["channels"].setdefault(week, "")
                record["genres"].setdefault(week, "")
                record["frequencies"].setdefault(week, None)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "records": sorted(
                records,
                key=lambda item: (
                    item["market"].lower(),
                    item["city"].lower(),
                    item["head_end"].lower(),
                    normalize_text(item.get("channel_name")).lower(),
                ),
            ),
            "message": "",
            "source_directory": str(history_path),
        }

    week_files = get_nbhd_week_files()
    if not week_files:
        return empty_nbhd_report()

    weekly_data = [prepare_nbhd_week_rows(path) for path in week_files]
    weeks = [label for label, _ in weekly_data]
    merged: dict[str, dict[str, Any]] = {}

    for week_label, rows in weekly_data:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((row["market"], row["city"], row["head_end"]), []).append(row)

        for (market, city, head_end), group_rows in grouped.items():
            for offset, nbhd_row in build_nbhd_channel_rows(group_rows):
                channel = normalize_text(nbhd_row["channel"])
                row_key = comparison_record_key(market, city, head_end, channel)
                record = merged.setdefault(
                    row_key,
                    {
                        "row_key": row_key,
                        "market": market,
                        "city": city,
                        "head_end": head_end,
                        "channel_name": channel,
                        "position": offset,
                        "positions": {},
                        "is_reference": False,
                        "channels": {},
                        "genres": {},
                        "frequencies": {},
                    },
                )
                if not normalize_text(record.get("channel_name")):
                    record["channel_name"] = channel
                record["position"] = offset
                record["positions"][week_label] = offset
                record["channels"][week_label] = channel
                record["genres"][week_label] = normalize_text(nbhd_row["genre"])
                record["frequencies"][week_label] = nbhd_row["frequency"]
                if channel.upper() in FOCUS_CHANNELS:
                    record["is_reference"] = True

    records = list(merged.values())
    for record in records:
        for week in weeks:
            record["channels"].setdefault(week, "")
            record["genres"].setdefault(week, "")
            record["frequencies"].setdefault(week, None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": sorted(
            records,
            key=lambda item: (
                item["market"].lower(),
                item["city"].lower(),
                item["head_end"].lower(),
                normalize_text(item.get("channel_name")).lower(),
            ),
        ),
        "message": "",
        "source_directory": str(get_nbhd_source_dir()),
    }


def load_nbhd_report(force: bool = False) -> dict[str, Any]:
    signature = get_history_signature() if history_files_ready() else get_signature(get_nbhd_week_files())
    if not force and NBHD_REPORT_CACHE["report"] is not None and NBHD_REPORT_CACHE["signature"] == signature:
        return NBHD_REPORT_CACHE["report"]

    report = build_nbhd_report()
    NBHD_REPORT_CACHE["signature"] = signature
    NBHD_REPORT_CACHE["report"] = report
    return report


def build_nbhd_benchmark_report() -> dict[str, Any]:
    if history_files_ready():
        history_path = resolve_history_path(HISTORY_NBHD_CSV, LEGACY_HISTORY_NBHD_CSV)
        dataframe = read_history_csv(history_path)
        if dataframe.empty:
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "weeks": [],
                "records": [],
                "message": "NBHD history CSV is empty.",
                "source_directory": str(history_path),
            }

        weeks = sorted(dataframe["Week"].dropna().astype(str).unique().tolist(), key=week_sort_key)
        merged: dict[str, dict[str, Any]] = {}
        for row in dataframe.to_dict(orient="records"):
            week_label = normalize_text(row.get("Week"))
            market = normalize_text(row.get("Market"))
            city = normalize_text(row.get("City"))
            head_end = normalize_text(row.get("Head-End"))
            channel = normalize_text(row.get("Channel"))
            if not market or not city or not head_end or not channel or not week_label:
                continue
            row_key = comparison_record_key(market, city, head_end, channel)
            record = merged.setdefault(
                row_key,
                {
                    "market": market,
                    "city": city,
                    "head_end": head_end,
                    "channel": channel,
                    "frequencies": {},
                },
            )
            record["frequencies"][week_label] = normalize_number(row.get("Frequency"))

        records = list(merged.values())
        for record in records:
            for week in weeks:
                record["frequencies"].setdefault(week, None)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "records": sorted(
                records,
                key=lambda item: (
                    item["market"].lower(),
                    item["city"].lower(),
                    item["head_end"].lower(),
                    item["channel"].lower(),
                ),
            ),
            "message": "",
            "source_directory": str(history_path),
        }

    week_files = get_nbhd_week_files()
    if not week_files:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": [],
            "records": [],
            "message": "Add weekly NBHD files to generate the INDIA TV comparison report.",
            "source_directory": str(get_nbhd_source_dir()),
        }

    weekly_data = [prepare_nbhd_week_rows(path) for path in week_files]
    weeks = [label for label, _ in weekly_data]
    merged: dict[str, dict[str, Any]] = {}

    for week_label, rows in weekly_data:
        for row in rows:
            market = normalize_text(row.get("market"))
            city = normalize_text(row.get("city"))
            head_end = normalize_text(row.get("head_end"))
            channel = normalize_text(row.get("channel"))
            if not market or not city or not head_end or not channel:
                continue
            row_key = comparison_record_key(market, city, head_end, channel)
            record = merged.setdefault(
                row_key,
                {
                    "market": market,
                    "city": city,
                    "head_end": head_end,
                    "channel": channel,
                    "frequencies": {},
                },
            )
            record["frequencies"][week_label] = row.get("frequency")

    records = list(merged.values())
    for record in records:
        for week in weeks:
            record["frequencies"].setdefault(week, None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": sorted(
            records,
            key=lambda item: (
                item["market"].lower(),
                item["city"].lower(),
                item["head_end"].lower(),
                item["channel"].lower(),
            ),
        ),
        "message": "",
        "source_directory": str(get_nbhd_source_dir()),
    }


def load_nbhd_benchmark_report(force: bool = False) -> dict[str, Any]:
    signature = get_history_signature() if history_files_ready() else get_signature(get_nbhd_week_files())
    if not force and NBHD_BENCHMARK_REPORT_CACHE["report"] is not None and NBHD_BENCHMARK_REPORT_CACHE["signature"] == signature:
        return NBHD_BENCHMARK_REPORT_CACHE["report"]

    report = build_nbhd_benchmark_report()
    NBHD_BENCHMARK_REPORT_CACHE["signature"] = signature
    NBHD_BENCHMARK_REPORT_CACHE["report"] = report
    return report


def build_ots_report() -> dict[str, Any]:
    if history_files_ready():
        history_path = resolve_history_path(HISTORY_OTS_CSV, LEGACY_HISTORY_OTS_CSV)
        dataframe = read_history_csv(history_path)
        if dataframe.empty:
            return empty_ots_report()

        weeks = sorted(dataframe["Week"].dropna().astype(str).unique().tolist(), key=week_sort_key)
        merged: dict[str, dict[str, Any]] = {}

        for week_label in weeks:
            week_frame = dataframe[dataframe["Week"].astype(str) == week_label]
            for row in week_frame.to_dict(orient="records"):
                market = normalize_text(row.get("Market"))
                channel = normalize_text(row.get("Channel"))
                if not market or not channel:
                    continue
                row_key = f"{market}||{channel}"
                record = merged.setdefault(
                    row_key,
                    {
                        "row_key": row_key,
                        "market": market,
                        "channel": channel,
                        "ots_values": {},
                    },
                )
                record["ots_values"][week_label] = normalize_ots_percentage(row.get("OTS"))

        records = list(merged.values())
        for record in records:
            for week in weeks:
                record["ots_values"].setdefault(week, None)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "records": sorted(records, key=lambda item: (item["market"].lower(), item["channel"].lower())),
            "message": "",
            "source_directory": str(history_path),
        }

    # Merge all weekly OTS workbooks into one dynamic week matrix keyed by market + channel.
    week_files = get_ots_week_files()
    if not week_files:
        return empty_ots_report()

    weekly_data = [prepare_ots_week_rows(path) for path in week_files]
    weeks = [label for label, _ in weekly_data]
    merged: dict[str, dict[str, Any]] = {}

    for week_label, rows in weekly_data:
        for row in rows:
            row_key = f"{row['market']}||{row['channel']}"
            record = merged.setdefault(
                row_key,
                {
                    "row_key": row_key,
                    "market": row["market"],
                    "channel": row["channel"],
                    "ots_values": {},
                },
            )
            record["ots_values"][week_label] = row["ots"]

    records = list(merged.values())
    for record in records:
        for week in weeks:
            record["ots_values"].setdefault(week, None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": sorted(records, key=lambda item: (item["market"].lower(), item["channel"].lower())),
        "message": "",
        "source_directory": str(get_ots_source_dir()),
    }


def load_ots_report(force: bool = False) -> dict[str, Any]:
    # Reuse a signature cache so repeated dashboard refreshes do not re-parse unchanged OTS files.
    signature = get_history_signature() if history_files_ready() else get_signature(get_ots_week_files())
    if not force and OTS_REPORT_CACHE["report"] is not None and OTS_REPORT_CACHE["signature"] == signature:
        return OTS_REPORT_CACHE["report"]

    report = build_ots_report()
    OTS_REPORT_CACHE["signature"] = signature
    OTS_REPORT_CACHE["report"] = report
    return report


def empty_report(message: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": [],
        "records": [],
        "message": message or "Add weekly Excel files to the data folder and refresh the dashboard.",
    }


def prepare_week_rows(path: Path, fallback_label: str) -> tuple[str, list[dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    rows: list[dict[str, Any]] = []
    parsed_week = parse_workbook_week(path)
    week_label = format_week_label(*reversed(parsed_week)) if parsed_week else fallback_label

    for row_index, values in enumerate(sheet.iter_rows(min_row=1, max_col=16, values_only=True), start=1):
        if row_index == 1:
            continue

        row = {
            SOURCE_COLUMNS[index]: values[index] if index < len(values) else None
            for index in range(len(SOURCE_COLUMNS))
        }

        if row_index == 2 and not parsed_week:
            candidate_week_label = normalize_text(row["WEEK LABEL"])
            if re.search(r"\bweek\b|\bwk\b", candidate_week_label, re.IGNORECASE):
                week_label = candidate_week_label

        normalized = {column: normalize_text(row.get(column)) for column in DISPLAY_COLUMNS if column != "NAME"}
        normalized["NAME"] = normalize_text(row.get("CHANNEL NAME"))
        normalized[FREQUENCY_COLUMN] = normalize_number(row.get(FREQUENCY_COLUMN))
        normalized[RANK_COLUMN] = normalize_rank(row.get(RANK_COLUMN))
        normalized["BAND"] = normalize_text(row.get("BAND"))
        normalized["TV CH. No."] = normalize_text(row.get("TV CH. No."))
        normalized["CRN No."] = normalize_text(row.get("CRN No."))
        normalized["ROW KEY"] = "||".join(normalized[column] for column in KEY_COLUMNS)

        if not normalized["ROW KEY"].replace("|", ""):
            continue

        rows.append(normalized)

    workbook.close()

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(row["ROW KEY"], row)
    return week_label, list(deduped.values())


def calculate_frequency_change(previous: float | int | None, current: float | int | None) -> str:
    if previous is None and current is None:
        return "missing"
    if previous is None and current is not None:
        return "increase"
    if previous is not None and current is None:
        return "decrease"
    if current > previous:
        return "increase"
    if current < previous:
        return "decrease"
    return "no_change"


def calculate_rank_change(previous: int | None, current: int | None) -> str:
    if previous is None and current is None:
        return "missing"
    if previous is None and current is not None:
        return "improve"
    if previous is not None and current is None:
        return "decline"
    if current < previous:
        return "improve"
    if current > previous:
        return "decline"
    return "no_change"


def calculate_band_change(previous: str | None, current: str | None) -> str:
    previous_text = normalize_text(previous)
    current_text = normalize_text(current)
    if not previous_text and not current_text:
        return "missing"
    if not previous_text and current_text:
        return "change"
    if previous_text and not current_text:
        return "change"
    if current_text == previous_text:
        return "no_change"
    return "change"


def has_any_change(series: dict[str, Any], weeks: list[str]) -> bool:
    values = [series.get(week) for week in weeks if series.get(week) not in (None, "")]
    return len(values) > 1 and len(set(values)) > 1


def build_report() -> dict[str, Any]:
    if history_files_ready():
        dataframe = read_history_csv(resolve_history_path(HISTORY_DISTRIBUTION_CSV, LEGACY_HISTORY_DISTRIBUTION_CSV))
        if dataframe.empty:
            report = empty_report()
            report["message"] = "Distribution history CSV is empty."
            return report

        weeks = sorted(dataframe["Week"].dropna().astype(str).unique().tolist(), key=week_sort_key)
        merged: dict[str, dict[str, Any]] = {}
        for row in dataframe.to_dict(orient="records"):
            transmission = normalize_text(row.get("Transmission"))
            market = normalize_text(row.get("Market"))
            mso_type = normalize_text(row.get("MSO Type"))
            city = normalize_text(row.get("City"))
            head_end = normalize_text(row.get("Head-End"))
            channel_name = normalize_text(row.get("Channel Name"))
            crn_no = normalize_text(row.get("CRN No."))
            row_key = "||".join((transmission, market, mso_type, city, head_end, channel_name, crn_no))
            if not row_key.replace("|", ""):
                continue

            week_label = normalize_text(row.get("Week"))
            record = merged.setdefault(
                row_key,
                {
                    "row_key": row_key,
                    "transmission": transmission,
                    "market": market,
                    "mso_type": mso_type,
                    "mso": transmission,
                    "city": city,
                    "head_end": head_end,
                    "channel_name": channel_name,
                    "band": normalize_text(row.get("Band")),
                    "tv_ch_no": normalize_text(row.get("TV CH. No.")),
                    "crn_no": crn_no,
                    "genre": normalize_text(row.get("Genre")),
                    "language": normalize_text(row.get("Language")),
                    "name": channel_name,
                    "week_label": week_label,
                    "frequencies": {},
                    "ranks": {},
                    "bands": {},
                    "changes": {},
                    "rank_changes": {},
                    "band_changes": {},
                },
            )
            record["frequencies"][week_label] = normalize_number(row.get("Frequency/LCN No"))
            record["ranks"][week_label] = normalize_rank(row.get("Rank Within Genre"))
            record["bands"][week_label] = normalize_text(row.get("Band"))

        records = list(merged.values())
        for record in records:
            for week in weeks:
                record["frequencies"].setdefault(week, None)
                record["ranks"].setdefault(week, None)
                record["bands"].setdefault(week, "")

            if weeks:
                first_week = weeks[0]
                record["changes"][first_week] = "baseline"
                record["rank_changes"][first_week] = "baseline"
                record["band_changes"][first_week] = "baseline"

            for index in range(1, len(weeks)):
                previous_week = weeks[index - 1]
                current_week = weeks[index]
                record["changes"][current_week] = calculate_frequency_change(
                    record["frequencies"][previous_week],
                    record["frequencies"][current_week],
                )
                record["rank_changes"][current_week] = calculate_rank_change(
                    record["ranks"][previous_week],
                    record["ranks"][current_week],
                )
                record["band_changes"][current_week] = calculate_band_change(
                    record["bands"][previous_week],
                    record["bands"][current_week],
                )

            record["change_status"] = "YES" if has_any_change(record["frequencies"], weeks) else "NO"
            record["rank_change_status"] = "YES" if has_any_change(record["ranks"], weeks) else "NO"
            record["band_change_status"] = "YES" if has_any_change(record["bands"], weeks) else "NO"

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "records": records,
            "message": "",
        }
        return report

    week_files = get_week_files()
    if not week_files:
        report = empty_report()
        report["message"] = "Add weekly Excel files to the data folder to generate the report."
        write_standalone_dashboard(report)
        return report

    weekly_data = [prepare_week_rows(path, path.stem) for path in week_files]
    weeks = [label for label, _ in weekly_data]

    merged: dict[str, dict[str, Any]] = {}
    for week_label, rows in weekly_data:
        for row in rows:
            record = merged.setdefault(
                row["ROW KEY"],
                {
                    "row_key": row["ROW KEY"],
                    "transmission": row["TRANSMISSION"],
                    "market": row["MARKET"],
                    "mso_type": row["MSO TYPE"],
                    "mso": row["TRANSMISSION"],
                    "city": row["CITY"],
                    "head_end": row["HEAD-END"],
                    "channel_name": row["CHANNEL NAME"],
                    "band": row["BAND"],
                    "tv_ch_no": row["TV CH. No."],
                    "crn_no": row["CRN No."],
                    "genre": row["GENRE"],
                    "language": row["LANGUAGE"],
                    "name": row["NAME"],
                    "week_label": row["WEEK LABEL"],
                    "frequencies": {},
                    "ranks": {},
                    "bands": {},
                    "changes": {},
                    "rank_changes": {},
                    "band_changes": {},
                },
            )
            record["frequencies"][week_label] = row[FREQUENCY_COLUMN]
            record["ranks"][week_label] = row[RANK_COLUMN]
            record["bands"][week_label] = row["BAND"]

    records = list(merged.values())

    for record in records:
        for week in weeks:
            record["frequencies"].setdefault(week, None)
            record["ranks"].setdefault(week, None)
            record["bands"].setdefault(week, "")

        if weeks:
            first_week = weeks[0]
            record["changes"][first_week] = "baseline"
            record["rank_changes"][first_week] = "baseline"
            record["band_changes"][first_week] = "baseline"

        for index in range(1, len(weeks)):
            previous_week = weeks[index - 1]
            current_week = weeks[index]
            record["changes"][current_week] = calculate_frequency_change(
                record["frequencies"][previous_week],
                record["frequencies"][current_week],
            )
            record["rank_changes"][current_week] = calculate_rank_change(
                record["ranks"][previous_week],
                record["ranks"][current_week],
            )
            record["band_changes"][current_week] = calculate_band_change(
                record["bands"][previous_week],
                record["bands"][current_week],
            )

        record["change_status"] = "YES" if has_any_change(record["frequencies"], weeks) else "NO"
        record["rank_change_status"] = "YES" if has_any_change(record["ranks"], weeks) else "NO"
        record["band_change_status"] = "YES" if has_any_change(record["bands"], weeks) else "NO"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": records,
        "message": "",
    }
    OUTPUT_JSON.write_text(compact_json_text(report), encoding="utf-8")
    write_standalone_dashboard(report)
    return report


def load_report(force: bool = False) -> dict[str, Any]:
    signature = get_history_signature() if history_files_ready() else get_signature(get_week_files())
    if not force and REPORT_CACHE["report"] is not None and REPORT_CACHE["signature"] == signature:
        return REPORT_CACHE["report"]

    report = build_report()
    REPORT_CACHE["signature"] = signature
    REPORT_CACHE["report"] = report
    return report


def normalize_frequency_cell(value: Any) -> float | int | None:
    text = normalize_text(value).upper()
    if text in {"", "NA", "N/A", "NOT AVAILABLE", "-"}:
        return None
    return normalize_number(value)


def comparison_record_key(market: str, city: str, head_end: str, channel: str) -> str:
    return "||".join(
        (
            normalize_text(market).upper(),
            normalize_text(city).upper(),
            normalize_text(head_end).upper(),
            normalize_text(channel).upper(),
        )
    )


def parse_weekly_highlight_sheet(path: Path) -> tuple[str, str, list[dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_name = "Weekly Highlights" if "Weekly Highlights" in workbook.sheetnames else "Weekly Highlight"
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"{path.name} does not contain a Weekly Highlights sheet.")

        sheet = workbook[sheet_name]
        header_row_index = None
        headers: list[Any] = []
        for row_index, row in enumerate(sheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1):
            row_values = list(row)
            header_keys = [normalize_header_key(value) for value in row_values]
            if {"MARKET", "CITY", "HEADEND", "CHANNEL"}.issubset(set(header_keys)):
                if sum(1 for value in row_values if "FREQUENCY" in normalize_text(value).upper()) >= 2:
                    header_row_index = row_index
                    headers = row_values
                    break

        if header_row_index is None:
            raise ValueError(f"Could not detect Weekly Highlights headers in {path.name}.")

        header_map = {normalize_header_key(value): index for index, value in enumerate(headers)}
        week_columns: list[tuple[int, int]] = []
        workbook_week = parse_workbook_week(path)
        workbook_year = workbook_week[0] if workbook_week else datetime.now().year

        for index, header in enumerate(headers):
            match = re.search(r"FREQUENCY\s*WK[-\s_]*(\d{1,2})", normalize_text(header), re.IGNORECASE)
            if match:
                week_columns.append((index, int(match.group(1))))

        if len(week_columns) < 2:
            raise ValueError(f"Could not detect two frequency week columns in Weekly Highlights for {path.name}.")

        week_columns = sorted(week_columns[:2], key=lambda item: item[1])
        previous_week_label = format_week_label(week_columns[0][1], workbook_year)
        current_week_label = format_week_label(week_columns[1][1], workbook_year)

        rows: list[dict[str, Any]] = []
        for values in sheet.iter_rows(min_row=header_row_index + 1, values_only=True):
            market = normalize_text(values[header_map["MARKET"]] if header_map["MARKET"] < len(values) else None)
            city = normalize_text(values[header_map["CITY"]] if header_map["CITY"] < len(values) else None)
            head_end = normalize_text(values[header_map["HEADEND"]] if header_map["HEADEND"] < len(values) else None)
            channel = normalize_text(values[header_map["CHANNEL"]] if header_map["CHANNEL"] < len(values) else None)
            if not market or not city or not head_end or not channel:
                continue
            rows.append(
                {
                    "market": market,
                    "city": city,
                    "head_end": head_end,
                    "channel": channel,
                    "frequency_previous": normalize_frequency_cell(values[week_columns[0][0]] if week_columns[0][0] < len(values) else None),
                    "frequency_current": normalize_frequency_cell(values[week_columns[1][0]] if week_columns[1][0] < len(values) else None),
                }
            )

        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            deduped.setdefault(
                comparison_record_key(row["market"], row["city"], row["head_end"], row["channel"]),
                row,
            )
        return previous_week_label, current_week_label, list(deduped.values())
    finally:
        workbook.close()


def build_comparison_report(report: dict[str, Any] | None = None) -> dict[str, Any]:
    frequency_report = report if report is not None else load_report(force=True)
    week_files = get_highlight_week_files()
    if not week_files:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": frequency_report.get("weeks", []),
            "pairs": [],
            "rows_by_pair": {},
            "message": "Add weekly workbook files to the data folder to generate the comparison table.",
        }

    rank_index = {
        comparison_record_key(record["market"], record["city"], record["head_end"], record["channel_name"]): record
        for record in frequency_report.get("records", [])
    }

    pairs: list[dict[str, Any]] = []
    rows_by_pair: dict[str, list[dict[str, Any]]] = {}
    available_weeks = set(frequency_report.get("weeks", []))

    for path in week_files:
        try:
            previous_week, current_week, highlight_rows = parse_weekly_highlight_sheet(path)
        except Exception:
            continue
        if previous_week not in available_weeks or current_week not in available_weeks:
            continue

        pair_key = f"{previous_week}||{current_week}"
        merged_rows: list[dict[str, Any]] = []
        for row in highlight_rows:
            record = rank_index.get(comparison_record_key(row["market"], row["city"], row["head_end"], row["channel"]))
            if not record:
                continue
            merged_rows.append(
                {
                    "market": row["market"],
                    "city": row["city"],
                    "head_end": row["head_end"],
                    "channel": row["channel"],
                    "frequency_previous": row["frequency_previous"],
                    "frequency_current": row["frequency_current"],
                    "rank_previous": record["ranks"].get(previous_week),
                    "rank_current": record["ranks"].get(current_week),
                }
            )

        merged_rows.sort(
            key=lambda item: (
                item["market"].lower(),
                item["city"].lower(),
                item["head_end"].lower(),
                item["channel"].lower(),
            )
        )
        rows_by_pair[pair_key] = merged_rows
        pairs.append(
            {
                "pair_key": pair_key,
                "week_from": previous_week,
                "week_to": current_week,
                "row_count": len(merged_rows),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": frequency_report.get("weeks", []),
        "pairs": sorted(pairs, key=lambda item: (week_sort_key(item["week_from"]), week_sort_key(item["week_to"]))),
        "rows_by_pair": rows_by_pair,
        "message": "",
    }


def load_comparison_report(force: bool = False, report: dict[str, Any] | None = None) -> dict[str, Any]:
    source_files = get_highlight_week_files()
    signature = get_signature(source_files) + tuple((f"report::{week}", index, index) for index, week in enumerate((report or load_report(force=False)).get("weeks", [])))
    if not force and COMPARISON_REPORT_CACHE["report"] is not None and COMPARISON_REPORT_CACHE["signature"] == signature:
        return COMPARISON_REPORT_CACHE["report"]

    comparison = build_comparison_report(report=report)
    COMPARISON_REPORT_CACHE["signature"] = signature
    COMPARISON_REPORT_CACHE["report"] = comparison
    return comparison


def get_view_config(view: str) -> dict[str, str]:
    if view == "rank":
        return {
            "series": "ranks",
            "changes": "rank_changes",
            "status": "rank_change_status",
            "positive": "improve",
            "negative": "decline",
            "positive_label": "improved",
            "negative_label": "declined",
        }
    if view == "band":
        return {
            "series": "bands",
            "changes": "band_changes",
            "status": "band_change_status",
            "positive": "change",
            "negative": "no_change",
            "positive_label": "changed",
            "negative_label": "stable",
        }
    return {
        "series": "frequencies",
        "changes": "changes",
        "status": "change_status",
        "positive": "increase",
        "negative": "decrease",
        "positive_label": "increased",
        "negative_label": "decreased",
    }


def filter_records(records: list[dict[str, Any]], view: str, filters: dict[str, str], ignore_key: str = "") -> list[dict[str, Any]]:
    config = get_view_config(view)
    changed_states = {"frequency": {"increase", "decrease"}, "rank": {"improve", "decline"}, "band": {"change"}}
    changed_set = changed_states.get(view, changed_states["frequency"])

    filtered: list[dict[str, Any]] = []
    for record in records:
        if filters["market"] and record["market"] != filters["market"] and ignore_key != "market":
            continue
        if filters["city"] and record["city"] != filters["city"] and ignore_key != "city":
            continue
        if ignore_key != "mso_type":
            if filters["mso_type"]:
                if record["mso_type"] != filters["mso_type"]:
                    continue
            else:
                if normalize_text(record.get("mso_type")).upper() == "DTH":
                    continue
        if filters["head_end"] and record["head_end"] != filters["head_end"] and ignore_key != "head_end":
            continue
        if filters["crn_no"] and record["crn_no"] != filters["crn_no"] and ignore_key != "crn_no":
            continue
        if filters["channel_name"] and record["channel_name"] != filters["channel_name"] and ignore_key != "channel_name":
            continue
        if filters["band"] and record["band"] != filters["band"] and ignore_key != "band":
            continue

        if ignore_key != "week" and filters["week"]:
            value = record[config["series"]].get(filters["week"])
            if value in (None, ""):
                continue

        if ignore_key != "change" and filters["change"]:
            if filters["change"] == "Changed":
                if filters["week"]:
                    if record[config["changes"]].get(filters["week"]) not in changed_set:
                        continue
                elif record[config["status"]] != "YES":
                    continue
            elif filters["change"] == "No Change":
                if filters["week"]:
                    if record[config["changes"]].get(filters["week"]) != "no_change":
                        continue
                elif record[config["status"]] != "NO":
                    continue

        filtered.append(record)

    return filtered


def sort_value(record: dict[str, Any], sort_key: str, view: str) -> Any:
    if sort_key == "flow_order":
        return (
            0,
            (
                str(record.get("market") or "").lower(),
                str(record.get("city") or "").lower(),
                str(record.get("head_end") or "").lower(),
                str(record.get("channel_name") or "").lower(),
            ),
        )
    if sort_key in record:
        value = record[sort_key]
    elif sort_key in record.get("frequencies", {}):
        config = get_view_config(view)
        value = record[config["series"]].get(sort_key)
    else:
        value = ""

    if value is None:
        return (1, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value).lower())


def sort_records(records: list[dict[str, Any]], sort_key: str, sort_direction: str, view: str) -> list[dict[str, Any]]:
    reverse = sort_direction == "desc"
    return sorted(records, key=lambda record: sort_value(record, sort_key, view), reverse=reverse)


def paginate_records(records: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total_count = len(records)
    if total_count == 0:
        return [], 0
    start = max(page - 1, 0) * page_size
    end = start + page_size
    return records[start:end], total_count


def build_filters(records: list[dict[str, Any]], view: str, current_filters: dict[str, str], weeks: list[str]) -> dict[str, list[str]]:
    def values_for(field: str) -> list[str]:
        values = {
            normalize_text(record.get(field))
            for record in records
            if normalize_text(record.get(field))
        }
        return sorted(values, key=lambda value: value.lower())

    return {
        "markets": values_for("market"),
        "cities": values_for("city"),
        "mso_types": values_for("mso_type"),
        "head_ends": values_for("head_end"),
        "crn_numbers": values_for("crn_no"),
        "channels": values_for("channel_name"),
        "bands": values_for("band"),
        "weeks": weeks,
        "change_options": ["Changed", "No Change"],
    }


def summarize_records(records: list[dict[str, Any]], view: str, weeks: list[str]) -> dict[str, int]:
    config = get_view_config(view)
    summary = {
        "total_channels": len(records),
    }

    positive = 0
    negative = 0
    stable = 0

    if view == "band":
        for record in records:
            if record[config["status"]] == "YES":
                positive += 1
            else:
                stable += 1
        summary["changed"] = positive
        summary["stable"] = stable
        return summary

    final_week = weeks[-1] if weeks else ""
    for record in records:
        status = record[config["changes"]].get(final_week, "no_change")
        if status == config["positive"]:
            positive += 1
        elif status == config["negative"]:
            negative += 1
        else:
            stable += 1

    if view == "rank":
        summary["improved"] = positive
        summary["declined"] = negative
        summary["no_change"] = stable
    else:
        summary["increased"] = positive
        summary["decreased"] = negative
        summary["no_change"] = stable
    return summary


def summarize_focus_channels(records: list[dict[str, Any]], view: str, weeks: list[str]) -> list[dict[str, Any]]:
    config = get_view_config(view)
    items: list[dict[str, Any]] = []

    for match_name, label in FOCUS_CHANNELS.items():
        selected = [record for record in records if normalize_text(record["channel_name"]).upper() == match_name]
        if not selected:
            continue

        positive = 0
        negative = 0
        no_change = 0
        latest_positive = 0
        latest_negative = 0
        latest_week = weeks[-1] if weeks else ""

        for record in selected:
            if not weeks:
                continue
            latest_status = record[config["changes"]].get(latest_week)
            if latest_status == config["positive"]:
                latest_positive += 1
            elif latest_status == config["negative"]:
                latest_negative += 1

            for week in weeks[1:]:
                status = record[config["changes"]].get(week)
                if status == config["positive"]:
                    positive += 1
                elif status == config["negative"]:
                    negative += 1
                elif status == "no_change":
                    no_change += 1

        items.append(
            {
                "label": label,
                "records": len(selected),
                "positive": positive,
                "negative": negative,
                "no_change": no_change,
                "latest_positive": latest_positive,
                "latest_negative": latest_negative,
                "latest_week": latest_week,
                "positive_label": config["positive_label"],
                "negative_label": config["negative_label"],
            }
        )

    return items


def serialize_records(records: list[dict[str, Any]], weeks: list[str]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for record in records:
        serialized.append(
            {
                "market": record["market"],
                "mso_type": record["mso_type"],
                "mso": record["mso"],
                "city": record["city"],
                "head_end": record["head_end"],
                "channel_name": record["channel_name"],
                "band": record["band"],
                "tv_ch_no": record["tv_ch_no"],
                "crn_no": record["crn_no"],
                "name": record["name"],
                "frequencies": {week: record["frequencies"].get(week) for week in weeks},
                "ranks": {week: record["ranks"].get(week) for week in weeks},
                "bands": {week: record["bands"].get(week) for week in weeks},
                "changes": {week: record["changes"].get(week, "missing") for week in weeks},
                "rank_changes": {week: record["rank_changes"].get(week, "missing") for week in weeks},
                "band_changes": {week: record["band_changes"].get(week, "missing") for week in weeks},
                "change_status": record["change_status"],
                "rank_change_status": record["rank_change_status"],
                "band_change_status": record["band_change_status"],
            }
        )
    return serialized


def read_style() -> str:
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return "body { font-family: sans-serif; }"


def read_nbhd_script() -> str:
    if NBHD_SCRIPT_FILE.exists():
        return NBHD_SCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def read_ots_script() -> str:
    if OTS_SCRIPT_FILE.exists():
        return OTS_SCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def read_comparison_script() -> str:
    if COMPARISON_SCRIPT_FILE.exists():
        return COMPARISON_SCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def read_nbhd_benchmark_script() -> str:
    if NBHD_BENCHMARK_SCRIPT_FILE.exists():
        return NBHD_BENCHMARK_SCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def read_landing_script() -> str:
    if LANDING_SCRIPT_FILE.exists():
        return LANDING_SCRIPT_FILE.read_text(encoding="utf-8")
    return ""


def load_landing_report(force: bool = False) -> dict[str, Any]:
    from landing_channel_tracker import process_landing_tracker_files

    needs_reprocess = not LANDING_HISTORY_CSV.exists()
    if LANDING_HISTORY_CSV.exists():
        try:
            check_df = pd.read_csv(LANDING_HISTORY_CSV, dtype=str)
            if check_df.empty or "Market" not in check_df.columns or check_df["Market"].dropna().str.strip().eq("").all():
                needs_reprocess = True
        except Exception:
            needs_reprocess = True

    if needs_reprocess:
        try:
            process_landing_tracker_files(force_reprocess=True)
        except Exception:
            pass

    if not LANDING_HISTORY_CSV.exists():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": [],
            "records": [],
            "message": "No landing data found.",
        }

    try:
        df = pd.read_csv(LANDING_HISTORY_CSV, dtype=str).fillna("")
    except Exception:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": [],
            "records": [],
            "message": "Failed to read landing data.",
        }

    if df.empty or "Week" not in df.columns:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": [],
            "records": [],
            "message": "Landing history is empty.",
        }

    weeks = sorted(
        list(df["Week"].unique()),
        key=lambda w: (
            int(re.search(r"\d+", w).group()) if re.search(r"\d+", w) else 0,
            w,
        ),
    )

    grouped: dict[tuple, dict[str, Any]] = {}
    for _, row in df.iterrows():
        sf_crn = str(row.get("SF CRN", row.get("SFRN NUMBER", ""))).strip()
        put_up_lcn = str(row.get("PUT-UP LCN", row.get("Popup LCN", ""))).strip()
        put_up_channel = str(row.get("PUT-UP CHANNEL", row.get("Popup Channel", ""))).strip()

        key = (
            row.get("Band", ""),
            row.get("Market", ""),
            row.get("City", ""),
            row.get("Headend", ""),
            row.get("State", ""),
            row.get("District", ""),
            row.get("Feed", ""),
            row.get("CRN NO", ""),
            sf_crn,
            row.get("MSO", ""),
        )
        if key not in grouped:
            grouped[key] = {
                "band": str(row.get("Band", "")).strip(),
                "market": str(row.get("Market", "")).strip(),
                "city": str(row.get("City", "")).strip(),
                "headend": str(row.get("Headend", "")).strip(),
                "state_name": str(row.get("State", "")).strip(),
                "district": str(row.get("District", "")).strip(),
                "feed": str(row.get("Feed", "")).strip(),
                "crn_no": str(row.get("CRN NO", "")).strip(),
                "sf_crn": sf_crn,
                "sfrn_number": sf_crn,
                "mso": str(row.get("MSO", "")).strip(),
                "put_up_lcn": put_up_lcn,
                "put_up_channel": put_up_channel,
                "weeks": {},
            }
        wk = str(row.get("Week", "")).strip()
        grouped[key]["weeks"][wk] = {
            "lcn_1": str(row.get("Landing 1 LCN", "")).strip(),
            "channel_1": str(row.get("Landing 1 Channel", row.get("Landing 1", ""))).strip(),
            "genre_1": str(row.get("Landing 1 Genre", "")).strip(),
            "lcn_2": str(row.get("Landing 2 LCN", "")).strip(),
            "channel_2": str(row.get("Landing 2 Channel", row.get("Landing 2", ""))).strip(),
            "genre_2": str(row.get("Landing 2 Genre", "")).strip(),
            "lcn_3": str(row.get("Landing 3 LCN", "")).strip(),
            "channel_3": str(row.get("Landing 3 Channel", row.get("Landing 3", ""))).strip(),
            "genre_3": str(row.get("Landing 3 Genre", "")).strip(),
            "lcn_b1": str(row.get("Barker 1 LCN", "")).strip(),
            "barker_1": str(row.get("Barker 1 Channel", row.get("Barker 1", ""))).strip(),
            "lcn_b2": str(row.get("Barker 2 LCN", "")).strip(),
            "barker_2": str(row.get("Barker 2 Channel", row.get("Barker 2", ""))).strip(),
            "put_up_lcn": put_up_lcn,
            "put_up_channel": put_up_channel,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": list(grouped.values()),
        "message": "",
    }


def compact_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def compact_inline_json(value: Any) -> str:
    return compact_json_text(value).replace("</", "<\\/")


def build_dashboard_bundle(report: dict[str, Any] | None = None) -> dict[str, Any]:
    frequency_report = report if report is not None else load_report(force=True)
    return {
        "frequency": frequency_report,
        "comparison": load_comparison_report(force=True, report=frequency_report),
        "nbhd_benchmark": load_nbhd_benchmark_report(force=True),
        "nbhd": build_nbhd_api_payload({"market": "", "city": "", "head_end": "", "channel": ""}, "", force_refresh=True),
        "nbhd_weekwise": load_nbhd_weekwise_report(force=True),
        "ots": build_ots_api_payload(
            {"markets": [], "channels": [], "week_from": "", "week_to": "", "change": "", "search": ""},
            force_refresh=True,
        ),
        "landing": load_landing_report(force=True),
    }


def write_frequency_report_json(report: dict[str, Any] | None = None) -> Path:
    bundle = build_dashboard_bundle(report)
    OUTPUT_JSON.write_text(f"window.__CHROME_REPORT_DATA__ = {compact_inline_json(bundle)};", encoding="utf-8")
    return OUTPUT_JSON


def read_landing_tracker_script() -> str:
    path = BASE_DIR / "static" / "landing_channel_tracker.js"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_nbhd_weekwise_script() -> str:
    return NBHD_WEEKWISE_SCRIPT_FILE.read_text(encoding="utf-8") if NBHD_WEEKWISE_SCRIPT_FILE.exists() else ""


def read_plotly_graph_script() -> str:
    path = BASE_DIR / "static" / "plotly_graph.js"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_plotly_graph_style() -> str:
    path = BASE_DIR / "static" / "plotly_graph.css"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_standalone_dashboard(report: dict[str, Any]) -> None:
    OUTPUT_HTML.write_text(create_standalone_dashboard(report), encoding="utf-8")


def create_standalone_dashboard(report: dict[str, Any]) -> str:
    dashboard_bundle = build_dashboard_bundle(report)
    embedded_bundle_script = f"window.__CHROME_REPORT_DATA__ = {compact_inline_json(dashboard_bundle)};"
    style_text = read_style()
    default_channel_reports_js = json.dumps(sort_summary_channels(["INDIA TV", "AAJ TAK", "NEWS 18 INDIA", "REPUBLIC BHARAT"]))
    nbhd_benchmark_script_text = read_nbhd_benchmark_script()
    nbhd_script_text = read_nbhd_script()
    nbhd_weekwise_script_text = read_nbhd_weekwise_script()
    ots_script_text = read_ots_script()
    comparison_script_text = read_comparison_script()
    landing_script_text = read_landing_script()
    landing_tracker_script_text = read_landing_tracker_script()
    plotly_script_text = read_plotly_graph_script()
    plotly_style_text = read_plotly_graph_style()

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Chrome Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
__STYLE__
  </style>
</head>
<body>
  <div class="app-shell">
    <div class="table1-scope">
      <section class="panel filter-panel">
        <div class="panel-heading"><div><h2>Filter Panel</h2></div></div>
        <div class="filter-grid">
          <label class="filter-select-field"><span>Market</span><div class="filter-select"><button id="marketFilter" class="filter-select-button" type="button">All Markets</button><div id="marketFilterMenu" class="filter-select-menu" hidden><input id="marketFilterSearch" class="filter-menu-search" type="text" placeholder="Search market..." autocomplete="off" /><div id="marketFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>City</span><div class="filter-select"><button id="cityFilter" class="filter-select-button" type="button">All Cities</button><div id="cityFilterMenu" class="filter-select-menu" hidden><input id="cityFilterSearch" class="filter-menu-search" type="text" placeholder="Search city..." autocomplete="off" /><div id="cityFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>MSO Type</span><div class="filter-select"><button id="msoTypeFilter" class="filter-select-button" type="button">All MSO Types</button><div id="msoTypeFilterMenu" class="filter-select-menu" hidden><input id="msoTypeFilterSearch" class="filter-menu-search" type="text" placeholder="Search MSO type..." autocomplete="off" /><div id="msoTypeFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Headend</span><div class="filter-select"><button id="headendFilter" class="filter-select-button" type="button">All Headend</button><div id="headendFilterMenu" class="filter-select-menu" hidden><input id="headendFilterSearch" class="filter-menu-search" type="text" placeholder="Search headend..." autocomplete="off" /><div id="headendFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>CRN No</span><div class="filter-select"><button id="crnFilter" class="filter-select-button" type="button">All CRN No</button><div id="crnFilterMenu" class="filter-select-menu" hidden><input id="crnFilterSearch" class="filter-menu-search" type="text" placeholder="Search CRN..." autocomplete="off" /><div id="crnFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Channel</span><div class="filter-select"><button id="channelFilter" class="filter-select-button" type="button">All Channels</button><div id="channelFilterMenu" class="filter-select-menu" hidden><input id="channelFilterSearch" class="filter-menu-search" type="text" placeholder="Search channel..." autocomplete="off" /><div id="channelFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Band</span><div class="filter-select"><button id="bandFilter" class="filter-select-button" type="button">All Bands</button><div id="bandFilterMenu" class="filter-select-menu" hidden><input id="bandFilterSearch" class="filter-menu-search" type="text" placeholder="Search band..." autocomplete="off" /><div id="bandFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>From Week</span><div class="filter-select"><button id="weekFromFilter" class="filter-select-button" type="button">From Week</button><div id="weekFromFilterMenu" class="filter-select-menu" hidden><input id="weekFromFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="weekFromFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>To Week</span><div class="filter-select"><button id="weekToFilter" class="filter-select-button" type="button">To Week</button><div id="weekToFilterMenu" class="filter-select-menu" hidden><input id="weekToFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="weekToFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Change</span><div class="filter-select"><button id="changeFilter" class="filter-select-button" type="button">All Changes</button><div id="changeFilterMenu" class="filter-select-menu" hidden><input id="changeFilterSearch" class="filter-menu-search" type="text" placeholder="Search change..." autocomplete="off" /><div id="changeFilterOptions" class="filter-options-list"></div></div></div></label>
          <div class="action-row table1-filter-actions">
            <button id="resetButton" class="ghost-button" type="button">Reset Filters</button>
            <button id="downloadTable1Button" class="ghost-button" type="button">Download Excel</button>
            <button id="fullscreenButton" class="primary-button" type="button">Full Screen</button>
          </div>
        </div>
      </section>

      <section class="panel table-panel">
        <div class="panel-heading table-heading">
          <div><h2 id="tableTitle">Weekly Frequency Analysis</h2></div>
          <div class="table-side">
            <div class="view-switcher">
              <button id="frequencyViewButton" class="switch-button active" type="button">Frequency</button>
              <button id="rankViewButton" class="switch-button" type="button">Rank</button>
              <button id="bandViewButton" class="switch-button" type="button">Band</button>
            </div>
            <div class="table-meta">
              <span id="resultCount">0 records</span>
              <span id="pageInfo">Page 1</span>
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="tableHead"></thead>
            <tbody id="tableBody"></tbody>
          </table>
        </div>
        <div class="pagination-bar">
          <button id="prevPage" class="ghost-button" type="button">Previous</button>
          <button id="exitFullscreenButton" class="ghost-button table-exit-fullscreen" type="button" hidden>Exit Full Screen</button>
          <button id="channelReportToggleButton" class="primary-button" type="button">Show Report</button>
          <button id="nextPage" class="ghost-button" type="button">Next</button>
        </div>
      </section>

      <section class="panel channel-report-panel">
        <div class="panel-heading">
          <div><h2>Channel Report</h2></div>
          <div class="table-meta">
            <span id="channelReportCount">0 channels</span>
          </div>
        </div>
        <div class="channel-report-toolbar">
          <label><span>Report Channel</span><select id="channelReportChannelFilter"></select></label>
          <label><span>MSO Type</span><select id="channelReportMsoTypeFilter"></select></label>
          <label><span>Week From</span><select id="channelReportWeekFromFilter"></select></label>
          <label><span>Week To</span><select id="channelReportWeekToFilter"></select></label>
          <div class="action-row channel-report-actions">
            <button id="channelReportResetButton" class="ghost-button" type="button">Reset</button>
            <button id="channelReportHideButton" class="ghost-button" type="button">Hide</button>
          </div>
        </div>
        <div id="channelReportContainer" class="channel-report-stack"></div>
      </section>

    </div>

    <section class="panel nbhd-panel">
      <div class="panel-heading nbhd-heading">
        <div><h2>Neighbourhood Comparison</h2></div>
        <div class="table-meta">
          <span id="nbhdResultCount">0 rows</span>
        </div>
      </div>
        <div class="nbhd-toolbar">
          <label class="filter-select-field"><span>Market</span><div class="filter-select"><button id="nbhdMarketFilter" class="filter-select-button" type="button">All Markets</button><div id="nbhdMarketFilterMenu" class="filter-select-menu" hidden><input id="nbhdMarketFilterSearch" class="filter-menu-search" type="text" placeholder="Search market..." autocomplete="off" /><div id="nbhdMarketFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>City</span><div class="filter-select"><button id="nbhdCityFilter" class="filter-select-button" type="button">All Cities</button><div id="nbhdCityFilterMenu" class="filter-select-menu" hidden><input id="nbhdCityFilterSearch" class="filter-menu-search" type="text" placeholder="Search city..." autocomplete="off" /><div id="nbhdCityFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Headend</span><div class="filter-select"><button id="nbhdHeadendFilter" class="filter-select-button" type="button">All Headends</button><div id="nbhdHeadendFilterMenu" class="filter-select-menu" hidden><input id="nbhdHeadendFilterSearch" class="filter-menu-search" type="text" placeholder="Search headend..." autocomplete="off" /><div id="nbhdHeadendFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>From Week</span><div class="filter-select"><button id="nbhdWeekFromFilter" class="filter-select-button" type="button">From Week</button><div id="nbhdWeekFromFilterMenu" class="filter-select-menu" hidden><input id="nbhdWeekFromFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="nbhdWeekFromFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>To Week</span><div class="filter-select"><button id="nbhdWeekToFilter" class="filter-select-button" type="button">To Week</button><div id="nbhdWeekToFilterMenu" class="filter-select-menu" hidden><input id="nbhdWeekToFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="nbhdWeekToFilterOptions" class="filter-options-list"></div></div></div></label>
          <label class="filter-select-field"><span>Change</span><div class="filter-select"><button id="nbhdChangeFilter" class="filter-select-button" type="button">All Changes</button><div id="nbhdChangeFilterMenu" class="filter-select-menu" hidden><input id="nbhdChangeFilterSearch" class="filter-menu-search" type="text" placeholder="Search change..." autocomplete="off" /><div id="nbhdChangeFilterOptions" class="filter-options-list"></div></div></div></label>
          <div class="action-row nbhd-actions">
            <button id="nbhdResetButton" class="ghost-button" type="button">Reset Filters</button>
            <button id="nbhdDownloadButton" class="ghost-button" type="button">Download Excel</button>
            <button id="nbhdFullscreenButton" class="primary-button" type="button">Full Screen</button>
            <button id="nbhdRefreshButton" class="ghost-button" type="button">Refresh</button>
          </div>
        </div>
        <div id="nbhdStatusMessage" class="status-message" hidden></div>
        <div class="nbhd-table-wrap">
          <table id="nbhdTable" class="nbhd-table">
            <thead id="nbhdTableHead"></thead>
            <tbody id="nbhdTableBody"></tbody>
        </table>
      </div>
      <div class="pagination-bar nbhd-pagination-bar">
        <button id="nbhdPrevPage" class="ghost-button" type="button">Previous</button>
        <span id="nbhdPageInfo">Page 1 of 1</span>
          <button id="nbhdNextPage" class="ghost-button" type="button">Next</button>
          <button id="nbhdExitFullscreenButton" class="ghost-button nbhd-exit-fullscreen" type="button" hidden>Exit Full Screen</button>
        </div>
        <div id="nbhdReportLauncher" class="nbhd-report-launcher">
          <button id="nbhdReportToggleButton" class="primary-button" type="button">Neighbour Change Report</button>
          <button id="nbhdComparisonReportToggleButton" class="ghost-button" type="button">India TV Genre Analysis</button>
          <button id="nbhdWeekwiseToggleButton" class="ghost-button" type="button">Weekly Analysis</button>
        </div>
        <section id="nbhdComparisonReportPanel" class="panel nbhd-report-panel" hidden>
          <div class="panel-heading nbhd-report-heading">
            <div>
              <h3>India TV Genre Positioning Analysis</h3>
              <p id="nbhdComparisonReportMeta" class="panel-subtitle">Automated analysis of India TV's position against the genres immediately above and below it.</p>
            </div>
            <div class="table-meta">
              <span id="nbhdComparisonReportCount">0 headends</span>
            </div>
          </div>
          <div class="action-row nbhd-comparison-report-actions">
            <button id="nbhdComparisonReportDownloadButton" class="ghost-button" type="button">Download Report</button>
            <button id="nbhdComparisonReportHideButton" class="primary-button" type="button">Hide</button>
          </div>
          <div id="nbhdComparisonReportStatusMessage" class="status-message" hidden></div>
          <div id="nbhdComparisonReportContent" class="nbhd-report-stack"></div>
        </section>
        <section id="nbhdReportPanel" class="panel nbhd-report-panel" hidden>
          <div class="panel-heading nbhd-report-heading">
            <div>
              <h3>Neighbour Change Report</h3>
              <p id="nbhdReportMeta" class="panel-subtitle">Compare changed neighbourhood positions for the default channels across all headends.</p>
            </div>
            <div class="table-meta">
              <span id="nbhdReportCount">0 narratives</span>
            </div>
          </div>
          <div class="nbhd-report-toolbar">
            <label class="filter-select-field"><span>Headend Name</span><div class="filter-select"><button id="nbhdReportHeadendFilter" class="filter-select-button" type="button">All Headends</button><div id="nbhdReportHeadendFilterMenu" class="filter-select-menu" hidden><input id="nbhdReportHeadendFilterSearch" class="filter-menu-search" type="text" placeholder="Search headend..." autocomplete="off" /><div id="nbhdReportHeadendFilterOptions" class="filter-options-list"></div></div></div></label>
            <label class="filter-select-field"><span>Channel</span><div class="filter-select"><button id="nbhdReportChannelFilter" class="filter-select-button" type="button">Default 4 Channels</button><div id="nbhdReportChannelFilterMenu" class="filter-select-menu" hidden><input id="nbhdReportChannelFilterSearch" class="filter-menu-search" type="text" placeholder="Search channel..." autocomplete="off" /><div id="nbhdReportChannelFilterOptions" class="filter-options-list"></div></div></div></label>
            <label class="filter-select-field"><span>Week From</span><div class="filter-select"><button id="nbhdReportWeekFromFilter" class="filter-select-button" type="button">Week From</button><div id="nbhdReportWeekFromFilterMenu" class="filter-select-menu" hidden><input id="nbhdReportWeekFromFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="nbhdReportWeekFromFilterOptions" class="filter-options-list"></div></div></div></label>
            <label class="filter-select-field"><span>Week To</span><div class="filter-select"><button id="nbhdReportWeekToFilter" class="filter-select-button" type="button">Week To</button><div id="nbhdReportWeekToFilterMenu" class="filter-select-menu" hidden><input id="nbhdReportWeekToFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="nbhdReportWeekToFilterOptions" class="filter-options-list"></div></div></div></label>
            <div class="action-row nbhd-report-actions">
              <button id="nbhdReportResetButton" class="ghost-button" type="button">Reset</button>
              <button id="nbhdReportHideButton" class="primary-button" type="button">Hide</button>
              <button id="nbhdReportDownloadButton" class="ghost-button" type="button">Download Report</button>
            </div>
          </div>
          <div id="nbhdReportStatusMessage" class="status-message" hidden></div>
          <div id="nbhdReportContent" class="nbhd-report-stack"></div>
        </section>
        <section id="nbhdWeekwisePanel" class="panel nbhd-weekwise-panel" hidden>
          <div class="panel-heading nbhd-weekwise-heading">
            <div>
              <h2>Week-wise Neighbourhood Comparison Report</h2>
              <p id="nbhdWeekwiseMeta" class="panel-subtitle">Filter by week, market, city, headend, channel, or genre with Excel-style multi-select controls.</p>
            </div>
            <div class="table-meta">
              <span id="nbhdWeekwiseResultCount">0 rows</span>
            </div>
          </div>
          <div class="comparison-toolbar nbhd-weekwise-toolbar">
            <div class="nbhd-weekwise-toolbar-meta">
              <span id="nbhdWeekwiseActiveFilters" class="nbhd-weekwise-summary-pill">All rows visible</span>
              <span id="nbhdWeekwiseTotalCount" class="nbhd-weekwise-summary-pill muted">0 total records</span>
            </div>
            <div class="action-row comparison-actions">
              <button id="nbhdWeekwiseResetButton" class="ghost-button" type="button">Reset All Filters</button>
              <button id="nbhdWeekwiseDownloadButton" class="ghost-button" type="button">Download Excel</button>
              <button id="nbhdWeekwiseHideButton" class="ghost-button" type="button">Hide</button>
              <button id="nbhdWeekwiseFullscreenButton" class="primary-button" type="button">Full Screen</button>
            </div>
          </div>
          <div id="nbhdWeekwiseStatusMessage" class="status-message" hidden></div>
          <div class="comparison-table-wrap nbhd-weekwise-table-wrap">
            <table id="nbhdWeekwiseTable" class="comparison-table nbhd-weekwise-table">
              <thead id="nbhdWeekwiseTableHead"></thead>
              <tbody id="nbhdWeekwiseTableBody"></tbody>
            </table>
          </div>
          <div class="pagination-bar comparison-pagination-bar nbhd-weekwise-footer">
            <span id="nbhdWeekwisePageInfo">Showing 0 of 0</span>
            <span id="nbhdWeekwiseLoadState" class="nbhd-weekwise-load-state">No data available.</span>
            <button id="nbhdWeekwiseExitFullscreenButton" class="ghost-button comparison-exit-fullscreen" type="button" hidden>Exit Full Screen</button>
          </div>
        </section>
      </section>

      <section class="panel ots-panel">
        <div class="panel-heading ots-heading">
          <div><h2>OTS Comparison</h2></div>
          <div class="table-meta">
            <span id="otsResultCount">0 records</span>
          </div>
        </div>
      <div class="ots-toolbar">
        <label class="ots-multiselect-field">
          <span>Market</span>
          <div class="ots-multiselect">
            <button id="otsMarketButton" class="ots-select-button" type="button">All Markets</button>
            <div id="otsMarketMenu" class="ots-multiselect-menu" hidden><input id="otsMarketSearch" class="ots-menu-search" type="text" placeholder="Search market..." autocomplete="off" /><div id="otsMarketOptions" class="ots-options-list"></div></div>
          </div>
        </label>
        <label class="ots-multiselect-field">
          <span>Channel</span>
          <div class="ots-multiselect">
            <button id="otsChannelButton" class="ots-select-button" type="button">All Channels</button>
            <div id="otsChannelMenu" class="ots-multiselect-menu" hidden><input id="otsChannelSearch" class="ots-menu-search" type="text" placeholder="Search channel..." autocomplete="off" /><div id="otsChannelOptions" class="ots-options-list"></div></div>
          </div>
        </label>
        <label class="filter-select-field"><span>Week From</span><div class="filter-select"><button id="otsWeekFromFilter" class="filter-select-button" type="button">From Week</button><div id="otsWeekFromFilterMenu" class="filter-select-menu" hidden><input id="otsWeekFromFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="otsWeekFromFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>Week To</span><div class="filter-select"><button id="otsWeekToFilter" class="filter-select-button" type="button">To Week</button><div id="otsWeekToFilterMenu" class="filter-select-menu" hidden><input id="otsWeekToFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="otsWeekToFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>Change</span><div class="filter-select"><button id="otsChangeFilter" class="filter-select-button" type="button">All Changes</button><div id="otsChangeFilterMenu" class="filter-select-menu" hidden><input id="otsChangeFilterSearch" class="filter-menu-search" type="text" placeholder="Search change..." autocomplete="off" /><div id="otsChangeFilterOptions" class="filter-options-list"></div></div></div></label>
        <div class="action-row ots-actions">
          <button id="otsResetButton" class="ghost-button" type="button">Reset Filters</button>
          <button id="otsDownloadButton" class="ghost-button" type="button">Download Excel</button>
          <button id="otsRefreshButton" class="ghost-button" type="button">Refresh</button>
          <button id="otsGraphButton" class="ghost-button" type="button">Graph</button>
          <button id="otsFullscreenButton" class="primary-button" type="button">Full Screen</button>
        </div>
      </div>
      <div id="otsStatusMessage" class="status-message" hidden></div>
      <div class="ots-table-wrap">
        <table id="otsTable" class="ots-table">
          <thead id="otsTableHead"></thead>
          <tbody id="otsTableBody"></tbody>
        </table>
      </div>
      <div id="otsGraphWrap" class="ots-graph-wrap" hidden>
        <div class="ots-graph-toolbar">
          <label class="ots-multiselect-field">
            <span>Market</span>
            <div class="ots-multiselect">
              <button id="otsGraphMarketButton" class="ots-select-button" type="button">Delhi</button>
              <div id="otsGraphMarketMenu" class="ots-multiselect-menu ots-graph-filter-menu" hidden>
                <div class="ots-graph-filter-head">
                  <strong>Market</strong>
                  <span id="otsGraphMarketSummary">All</span>
                </div>
                <input id="otsGraphMarketSearch" class="ots-menu-search" type="text" placeholder="Search market..." autocomplete="off" />
                <div id="otsGraphMarketOptions" class="ots-options-list"></div>
              </div>
            </div>
          </label>
          <label class="ots-multiselect-field">
            <span>Channel</span>
            <div class="ots-multiselect">
              <button id="otsGraphChannelButton" class="ots-select-button" type="button">4 selected</button>
              <div id="otsGraphChannelMenu" class="ots-multiselect-menu ots-graph-filter-menu" hidden>
                <div class="ots-graph-filter-head">
                  <strong>Channel</strong>
                  <span id="otsGraphChannelSummary">4 selected</span>
                </div>
                <input id="otsGraphChannelSearch" class="ots-menu-search" type="text" placeholder="Search channel..." autocomplete="off" />
                <div class="ots-graph-filter-actions">
                  <button id="otsGraphChannelSelectAll" class="ghost-button" type="button">Select All</button>
                  <button id="otsGraphChannelClear" class="ghost-button" type="button">Clear</button>
                </div>
                <div id="otsGraphChannelOptions" class="ots-options-list"></div>
              </div>
            </div>
          </label>
          <div class="action-row ots-graph-actions">
            <button id="otsGraphCloseButton" class="ghost-button" type="button">Close Graph</button>
          </div>
        </div>
        <div id="otsGraphLoading" class="ots-graph-loading">Loading chart...</div>
        <div id="otsGraphEmpty" class="ots-graph-empty" hidden></div>
        <div id="otsGraphContainer"></div>
      </div>
      <div class="pagination-bar ots-pagination-bar">
        <button id="otsPrevPage" class="ghost-button" type="button">Previous</button>
        <span id="otsPageInfo">Page 1 of 1</span>
        <button id="otsNextPage" class="ghost-button" type="button">Next</button>
        <button id="otsExitFullscreenButton" class="ghost-button ots-exit-fullscreen" type="button" hidden>Exit Full Screen</button>
      </div>
      <div id="otsReportLauncher" class="ots-report-launcher">
        <button id="otsReportToggleButton" class="primary-button" type="button">Show Report</button>
      </div>
      <section id="otsReportPanel" class="panel ots-report-panel" hidden>
        <div class="panel-heading ots-report-heading">
          <div>
            <h3>OTS Change Report</h3>
            <p id="otsReportMeta" class="panel-subtitle">Compare channel-wise OTS movement between the previous and current visible weeks.</p>
          </div>
          <div class="table-meta">
            <span id="otsReportCount">0 narratives</span>
          </div>
        </div>
        <div class="ots-report-toolbar">
          <label class="ots-multiselect-field">
            <span>Market</span>
            <div class="ots-multiselect">
              <button id="otsReportMarketFilter" class="ots-select-button" type="button">All Markets</button>
              <div id="otsReportMarketFilterMenu" class="ots-multiselect-menu" hidden>
                <input id="otsReportMarketFilterSearch" class="filter-menu-search" type="text" placeholder="Search market..." autocomplete="off" />
                <div id="otsReportMarketFilterOptions" class="ots-options-list"></div>
              </div>
            </div>
          </label>
          <label class="ots-multiselect-field">
            <span>Channel</span>
            <div class="ots-multiselect">
              <button id="otsReportChannelFilter" class="ots-select-button" type="button">Default 4 Channels</button>
              <div id="otsReportChannelFilterMenu" class="ots-multiselect-menu" hidden>
                <input id="otsReportChannelFilterSearch" class="filter-menu-search" type="text" placeholder="Search channel..." autocomplete="off" />
                <div id="otsReportChannelFilterOptions" class="ots-options-list"></div>
              </div>
            </div>
          </label>
          <div class="action-row ots-report-actions">
            <button id="otsReportResetButton" class="ghost-button" type="button">Reset</button>
            <button id="otsReportHideButton" class="primary-button" type="button">Hide</button>
          </div>
        </div>
        <div id="otsReportStatusMessage" class="status-message" hidden></div>
        <div id="otsReportContent" class="ots-report-stack"></div>
      </section>

    <section class="panel comparison-panel">
      <div class="panel-heading comparison-heading">
        <div><h2>Weekly Frequency & Rank Comparison</h2></div>
        <div class="table-meta">
          <span id="comparisonResultCount">0 rows</span>
        </div>
      </div>
      <div class="comparison-toolbar">
        <label class="filter-select-field"><span>Market</span><div class="filter-select"><button id="comparisonMarketFilter" class="filter-select-button" type="button">All Markets</button><div id="comparisonMarketFilterMenu" class="filter-select-menu" hidden><input id="comparisonMarketFilterSearch" class="filter-menu-search" type="text" placeholder="Search market..." autocomplete="off" /><div id="comparisonMarketFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>City</span><div class="filter-select"><button id="comparisonCityFilter" class="filter-select-button" type="button">All Cities</button><div id="comparisonCityFilterMenu" class="filter-select-menu" hidden><input id="comparisonCityFilterSearch" class="filter-menu-search" type="text" placeholder="Search city..." autocomplete="off" /><div id="comparisonCityFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>Headend</span><div class="filter-select"><button id="comparisonHeadendFilter" class="filter-select-button" type="button">All Headends</button><div id="comparisonHeadendFilterMenu" class="filter-select-menu" hidden><input id="comparisonHeadendFilterSearch" class="filter-menu-search" type="text" placeholder="Search headend..." autocomplete="off" /><div id="comparisonHeadendFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>Channel</span><div class="filter-select"><button id="comparisonChannelFilter" class="filter-select-button" type="button">All Channels</button><div id="comparisonChannelFilterMenu" class="filter-select-menu" hidden><input id="comparisonChannelFilterSearch" class="filter-menu-search" type="text" placeholder="Search channel..." autocomplete="off" /><div id="comparisonChannelFilterOptions" class="filter-options-list"></div></div></div></label>
        <label class="filter-select-field"><span>Week</span><div class="filter-select"><button id="comparisonWeekFilter" class="filter-select-button" type="button">Select Week</button><div id="comparisonWeekFilterMenu" class="filter-select-menu" hidden><input id="comparisonWeekFilterSearch" class="filter-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="comparisonWeekFilterOptions" class="filter-options-list"></div></div></div></label>
        <div class="action-row comparison-actions">
          <button id="comparisonResetButton" class="ghost-button" type="button">Reset Filters</button>
          <button id="comparisonDownloadButton" class="ghost-button" type="button">Download Excel</button>
          <button id="comparisonFullscreenButton" class="primary-button" type="button">Full Screen</button>
        </div>
      </div>
      <div id="comparisonStatusMessage" class="status-message" hidden></div>
      <div class="comparison-table-wrap">
        <table id="comparisonTable" class="comparison-table">
          <thead id="comparisonTableHead"></thead>
          <tbody id="comparisonTableBody"></tbody>
        </table>
      </div>
      <div class="pagination-bar comparison-pagination-bar">
        <button id="comparisonPrevPage" class="ghost-button" type="button">Previous</button>
        <span id="comparisonPageInfo">Page 1 of 1</span>
        <button id="comparisonNextPage" class="ghost-button" type="button">Next</button>
        <button id="comparisonExitFullscreenButton" class="ghost-button comparison-exit-fullscreen" type="button" hidden>Exit Full Screen</button>
      </div>
    </section>

    <section class="panel landing-tracker-panel">
      <div class="panel-heading landing-tracker-heading">
        <div><h2>Landing Channel Change Tracker</h2></div>
      </div>
      <div class="landing-tracker-toolbar">
        <div class="tracker-field"><span class="tracker-field-label">Band</span><div class="filter-select"><button id="trackerBandFilter" class="tracker-select-btn" type="button">All Bands</button><div id="trackerBandFilterMenu" class="tracker-menu" hidden><input id="trackerBandFilterSearch" class="tracker-menu-search" type="text" placeholder="Search band..." autocomplete="off" /><div id="trackerBandFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Market</span><div class="filter-select"><button id="trackerMarketFilter" class="tracker-select-btn" type="button">All Markets</button><div id="trackerMarketFilterMenu" class="tracker-menu" hidden><input id="trackerMarketFilterSearch" class="tracker-menu-search" type="text" placeholder="Search market..." autocomplete="off" /><div id="trackerMarketFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">City</span><div class="filter-select"><button id="trackerCityFilter" class="tracker-select-btn" type="button">All Cities</button><div id="trackerCityFilterMenu" class="tracker-menu" hidden><input id="trackerCityFilterSearch" class="tracker-menu-search" type="text" placeholder="Search city..." autocomplete="off" /><div id="trackerCityFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Headend</span><div class="filter-select"><button id="trackerHeadendFilter" class="tracker-select-btn" type="button">All Headends</button><div id="trackerHeadendFilterMenu" class="tracker-menu" hidden><input id="trackerHeadendFilterSearch" class="tracker-menu-search" type="text" placeholder="Search headend..." autocomplete="off" /><div id="trackerHeadendFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">State</span><div class="filter-select"><button id="trackerStateFilter" class="tracker-select-btn" type="button">All States</button><div id="trackerStateFilterMenu" class="tracker-menu" hidden><input id="trackerStateFilterSearch" class="tracker-menu-search" type="text" placeholder="Search state..." autocomplete="off" /><div id="trackerStateFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">District</span><div class="filter-select"><button id="trackerDistrictFilter" class="tracker-select-btn" type="button">All Districts</button><div id="trackerDistrictFilterMenu" class="tracker-menu" hidden><input id="trackerDistrictFilterSearch" class="tracker-menu-search" type="text" placeholder="Search district..." autocomplete="off" /><div id="trackerDistrictFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Feed</span><div class="filter-select"><button id="trackerFeedFilter" class="tracker-select-btn" type="button">All Feeds</button><div id="trackerFeedFilterMenu" class="tracker-menu" hidden><input id="trackerFeedFilterSearch" class="tracker-menu-search" type="text" placeholder="Search feed..." autocomplete="off" /><div id="trackerFeedFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">MSO</span><div class="filter-select"><button id="trackerMsoFilter" class="tracker-select-btn" type="button">All MSO</button><div id="trackerMsoFilterMenu" class="tracker-menu" hidden><input id="trackerMsoFilterSearch" class="tracker-menu-search" type="text" placeholder="Search MSO..." autocomplete="off" /><div id="trackerMsoFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Channel Type</span><div class="filter-select"><button id="trackerChannelTypeFilter" class="tracker-select-btn" type="button">Landing Channel 1</button><div id="trackerChannelTypeFilterMenu" class="tracker-menu" hidden><input id="trackerChannelTypeFilterSearch" class="tracker-menu-search" type="text" placeholder="Search channel type..." autocomplete="off" /><div id="trackerChannelTypeFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Week From</span><div class="filter-select"><button id="trackerWeekFromFilter" class="tracker-select-btn" type="button">Week From</button><div id="trackerWeekFromFilterMenu" class="tracker-menu" hidden><input id="trackerWeekFromFilterSearch" class="tracker-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="trackerWeekFromFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Week To</span><div class="filter-select"><button id="trackerWeekToFilter" class="tracker-select-btn" type="button">Week To</button><div id="trackerWeekToFilterMenu" class="tracker-menu" hidden><input id="trackerWeekToFilterSearch" class="tracker-menu-search" type="text" placeholder="Search week..." autocomplete="off" /><div id="trackerWeekToFilterOptions" class="tracker-options-list"></div></div></div></div>
        <div class="tracker-field"><span class="tracker-field-label">Change</span><div class="filter-select"><button id="trackerChangeFilter" class="tracker-select-btn" type="button">All Changes</button><div id="trackerChangeFilterMenu" class="tracker-menu" hidden><input id="trackerChangeFilterSearch" class="tracker-menu-search" type="text" placeholder="Search change..." autocomplete="off" /><div id="trackerChangeFilterOptions" class="tracker-options-list"></div></div></div></div>

        <div class="landing-tracker-actions">
          <button id="trackerResetButton" class="ghost-button" type="button">Reset</button>
          <button id="trackerDownloadButton" class="ghost-button" type="button">Download Excel</button>
          <button id="trackerFullscreenButton" class="primary-button" type="button">Full Screen</button>
        </div>
      </div>

      <div class="landing-tracker-table-wrap">
        <table class="landing-tracker-table" id="landingTrackerTable">
          <thead id="landingTrackerTableHead"></thead>
          <tbody id="landingTrackerTableBody"></tbody>
        </table>
      </div>

      <div class="pagination-bar">
        <button id="trackerPrevPage" class="ghost-button" type="button">Previous</button>
        <span id="trackerPageInfo">Page 1</span>
        <span id="trackerResultCount" style="font-size:0.75rem; color:var(--muted); margin:0 8px;">0 records</span>
        <button id="trackerNextPage" class="ghost-button" type="button">Next</button>
      </div>
    </section>



    <section class="kpi-grid bottom-kpis">
      <article class="kpi-card compact-kpi">
        <span>Total Rows</span>
        <strong id="kpiTotalRows">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total Market</span>
        <strong id="kpiTotalMarket">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total City</span>
        <strong id="kpiTotalCity">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total MSO Type</span>
        <strong id="kpiTotalMsoType">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total Headend</span>
        <strong id="kpiTotalHeadend">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total Channel</span>
        <strong id="kpiTotalChannel">0</strong>
      </article>
      <article class="kpi-card compact-kpi">
        <span>Total Band</span>
        <strong id="kpiTotalBand">0</strong>
      </article>
    </section>

    <section class="download-bar">
      <button id="downloadDashboardButton" class="ghost-button" type="button">Download Dashboard</button>
    </section>
  </div>

  <template id="emptyStateTemplate">
    <tr><td colspan="100%" class="empty-state">No records match the current filters.</td></tr>
  </template>

  <script>
__EMBEDDED_BUNDLE_SCRIPT__
  </script>
  <script>
const reportBundle = window.__CHROME_REPORT_DATA__ || {
  frequency: { generated_at: "", weeks: [], records: [], message: "Dashboard data file could not be loaded." },
  comparison: { generated_at: "", weeks: [], pairs: [], rows_by_pair: {}, message: "Comparison data file could not be loaded." },
  nbhd_benchmark: { generated_at: "", weeks: [], records: [], message: "INDIA TV comparison data file could not be loaded.", source_directory: "" },
  nbhd: { generated_at: "", weeks: [], filters: { markets: [], cities: [], head_ends: [], channels: [] }, table: { records: [], total_count: 0 }, message: "Neighbourhood data file could not be loaded.", source_directory: "" },
  ots: { generated_at: "", weeks: [], visible_weeks: [], filters: { markets: [], channels: [] }, table: { records: [], total_count: 0 }, message: "OTS data file could not be loaded.", source_directory: "" },
  landing: { generated_at: "", weeks: [], records: [], message: "Landing data file could not be loaded." }
};
const report = reportBundle.frequency;
function sanitizeSheetName(value, fallback = "Sheet1") {
  const text = String(value || "").replace(/[\\/*?:\\[\\]]/g, " ").trim();
  return (text || fallback).slice(0, 31);
}
function escapeExcelXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
function excelCell(value, style = "cell", options = {}) {
  return { value, style, ...options };
}
function excelRow(values, style = "cell") {
  return (Array.isArray(values) ? values : []).map((value) => {
    if (value && typeof value === "object" && !Array.isArray(value) && Object.prototype.hasOwnProperty.call(value, "value")) {
      return value;
    }
    return excelCell(value, style);
  });
}
function blankExcelRow(cellCount = 1) {
  return Array.from({ length: Math.max(1, cellCount) }, () => excelCell("", "cell"));
}
function coerceExcelCell(cell) {
  if (cell && typeof cell === "object" && !Array.isArray(cell) && Object.prototype.hasOwnProperty.call(cell, "value")) {
    return cell;
  }
  return excelCell(cell);
}
function columnIndexToLetters(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}
function xlsxCellRef(rowIndex, columnIndex) {
  return `${columnIndexToLetters(columnIndex)}${rowIndex + 1}`;
}
function xlsxEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
const XLSX_STYLE_INDEX = {
  title: 1,
  meta: 2,
  group: 3,
  header: 4,
  cell: 5,
  textWrap: 6,
  number: 7,
  positive: 8,
  negative: 9,
  neutral: 10,
  highlight: 11,
  missing: 12,
  changeYes: 13,
  changeNo: 14,
  altRow: 15,
  altRowWrap: 16,
};
function buildXlsxStylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="8">
    <font><sz val="11"/><color rgb="FF25324B"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="13"/><color rgb="FF1F2A44"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF1F2A44"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF1A2F6B"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF13284B"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF15803D"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FFDC2626"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF8A6D1F"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="10">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF1FF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF4F8FF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE8F8EF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFDEAEA"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEFF6FF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFFDF0"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF1F5FB"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFD"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFD7E1F0"/></left>
      <right style="thin"><color rgb="FFD7E1F0"/></right>
      <top style="thin"><color rgb="FFD7E1F0"/></top>
      <bottom style="thin"><color rgb="FFD7E1F0"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="17">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="4" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="5" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="6" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="7" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="6" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="5" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>`;
}
function buildXlsxWorksheetXml(sheet) {
  const rows = Array.isArray(sheet?.rows) ? sheet.rows : [];
  const occupied = new Set();
  const merges = [];
  const rowXml = [];
  let maxColumn = 0;
  rows.forEach((row, rowIndex) => {
    let logicalColumn = 0;
    const cellXml = [];
    (Array.isArray(row) ? row : []).forEach((rawCell) => {
      while (occupied.has(`${rowIndex}:${logicalColumn}`)) logicalColumn += 1;
      const cell = coerceExcelCell(rawCell);
      const mergeAcross = Number.isInteger(cell.mergeAcross) && cell.mergeAcross > 0 ? cell.mergeAcross : 0;
      const mergeDown = Number.isInteger(cell.mergeDown) && cell.mergeDown > 0 ? cell.mergeDown : 0;
      const cellRef = xlsxCellRef(rowIndex, logicalColumn);
      const styleIndex = XLSX_STYLE_INDEX[cell.style] ?? XLSX_STYLE_INDEX.cell;
      const value = cell.value;
      const isNumber = cell.type === "number" || (typeof value === "number" && Number.isFinite(value));
      if (mergeAcross || mergeDown) {
        merges.push(`${cellRef}:${xlsxCellRef(rowIndex + mergeDown, logicalColumn + mergeAcross)}`);
        for (let r = rowIndex; r <= rowIndex + mergeDown; r += 1) {
          for (let c = logicalColumn; c <= logicalColumn + mergeAcross; c += 1) {
            if (r === rowIndex && c === logicalColumn) continue;
            occupied.add(`${r}:${c}`);
          }
        }
      }
      if (!(value === null || value === undefined || value === "")) {
        if (isNumber) {
          cellXml.push(`<c r="${cellRef}" s="${styleIndex}"><v>${value}</v></c>`);
        } else {
          cellXml.push(`<c r="${cellRef}" s="${styleIndex}" t="inlineStr"><is><t>${xlsxEscape(value)}</t></is></c>`);
        }
      } else if (styleIndex !== XLSX_STYLE_INDEX.cell) {
        cellXml.push(`<c r="${cellRef}" s="${styleIndex}" t="inlineStr"><is><t></t></is></c>`);
      }
      logicalColumn += mergeAcross + 1;
      maxColumn = Math.max(maxColumn, logicalColumn);
    });
    if (cellXml.length) {
      rowXml.push(`<row r="${rowIndex + 1}">${cellXml.join("")}</row>`);
    }
  });
  const colsXml = (Array.isArray(sheet?.columns) ? sheet.columns : []).map((column, index) => {
    const width = Number(column?.width || column);
    return Number.isFinite(width)
      ? `<col min="${index + 1}" max="${index + 1}" width="${Math.max(8, width / 7.2).toFixed(2)}" customWidth="1"/>`
      : "";
  }).join("");
  const mergeXml = merges.length ? `<mergeCells count="${merges.length}">${merges.map((ref) => `<mergeCell ref="${ref}"/>`).join("")}</mergeCells>` : "";
  const dimensionRef = maxColumn > 0 && rows.length > 0 ? `A1:${xlsxCellRef(Math.max(rows.length - 1, 0), Math.max(maxColumn - 1, 0))}` : "A1";
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="${dimensionRef}"/>
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  ${colsXml ? `<cols>${colsXml}</cols>` : ""}
  <sheetData>${rowXml.join("")}</sheetData>
  ${mergeXml}
</worksheet>`;
}
function buildXlsxWorkbookParts(sheets) {
  const safeSheets = (Array.isArray(sheets) ? sheets : []).filter((sheet) => Array.isArray(sheet?.rows));
  const worksheetParts = safeSheets.map((sheet, index) => ({
    path: `xl/worksheets/sheet${index + 1}.xml`,
    content: buildXlsxWorksheetXml(sheet),
  }));
  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    ${safeSheets.map((sheet, index) => `<sheet name="${xlsxEscape(sanitizeSheetName(sheet.name, `Sheet${index + 1}`))}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join("")}
  </sheets>
</workbook>`;
  const workbookRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  ${safeSheets.map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`).join("")}
  <Relationship Id="rId${safeSheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;
  const contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  ${safeSheets.map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}
</Types>`;
  const rootRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
  return [
    { path: "[Content_Types].xml", content: contentTypesXml },
    { path: "_rels/.rels", content: rootRelsXml },
    { path: "xl/workbook.xml", content: workbookXml },
    { path: "xl/_rels/workbook.xml.rels", content: workbookRelsXml },
    { path: "xl/styles.xml", content: buildXlsxStylesXml() },
    ...worksheetParts,
  ];
}
function crc32(bytes) {
  const table = crc32.table || (crc32.table = (() => {
    const values = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let current = index;
      for (let bit = 0; bit < 8; bit += 1) {
        current = (current & 1) ? (0xEDB88320 ^ (current >>> 1)) : (current >>> 1);
      }
      values[index] = current >>> 0;
    }
    return values;
  })());
  let value = 0xFFFFFFFF;
  for (let index = 0; index < bytes.length; index += 1) {
    value = table[(value ^ bytes[index]) & 0xFF] ^ (value >>> 8);
  }
  return (value ^ 0xFFFFFFFF) >>> 0;
}
function concatUint8Arrays(chunks) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  chunks.forEach((chunk) => {
    result.set(chunk, offset);
    offset += chunk.length;
  });
  return result;
}
function uint16LE(value) {
  return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF]);
}
function uint32LE(value) {
  return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF, (value >>> 16) & 0xFF, (value >>> 24) & 0xFF]);
}
async function deflateRaw(bytes) {
  if (typeof CompressionStream === "undefined") return null;
  try {
    const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate-raw"));
    const buffer = await new Response(stream).arrayBuffer();
    return new Uint8Array(buffer);
  } catch (_error) {
    return null;
  }
}
async function buildZip(files) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    const nameBytes = encoder.encode(file.path);
    const contentBytes = encoder.encode(file.content);
    const compressed = await deflateRaw(contentBytes);
    const useCompression = compressed && compressed.length < contentBytes.length;
    const body = useCompression ? compressed : contentBytes;
    const method = useCompression ? 8 : 0;
    const checksum = crc32(contentBytes);
    const localHeader = concatUint8Arrays([
      uint32LE(0x04034B50),
      uint16LE(20),
      uint16LE(0),
      uint16LE(method),
      uint16LE(0),
      uint16LE(0),
      uint32LE(checksum),
      uint32LE(body.length),
      uint32LE(contentBytes.length),
      uint16LE(nameBytes.length),
      uint16LE(0),
      nameBytes,
    ]);
    localParts.push(localHeader, body);
    const centralHeader = concatUint8Arrays([
      uint32LE(0x02014B50),
      uint16LE(20),
      uint16LE(20),
      uint16LE(0),
      uint16LE(method),
      uint16LE(0),
      uint16LE(0),
      uint32LE(checksum),
      uint32LE(body.length),
      uint32LE(contentBytes.length),
      uint16LE(nameBytes.length),
      uint16LE(0),
      uint16LE(0),
      uint16LE(0),
      uint16LE(0),
      uint32LE(0),
      uint32LE(offset),
      nameBytes,
    ]);
    centralParts.push(centralHeader);
    offset += localHeader.length + body.length;
  }
  const centralDirectory = concatUint8Arrays(centralParts);
  const endRecord = concatUint8Arrays([
    uint32LE(0x06054B50),
    uint16LE(0),
    uint16LE(0),
    uint16LE(files.length),
    uint16LE(files.length),
    uint32LE(centralDirectory.length),
    uint32LE(offset),
    uint16LE(0),
  ]);
  return concatUint8Arrays([...localParts, centralDirectory, endRecord]);
}
async function downloadExcelWorkbook(filename, sheets) {
  const zipBytes = await buildZip(buildXlsxWorkbookParts(sheets));
  const blob = new Blob([zipBytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const safeName = filename.replace(/\\.xls$/i, "").replace(/\\.xlsx$/i, "");
  link.download = `${safeName}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
window.__downloadExcelWorkbook = downloadExcelWorkbook;
window.__excelCell = excelCell;
window.__excelRow = excelRow;
window.__blankExcelRow = blankExcelRow;
function normalizeWeeks(weeks) {
  return Array.isArray(weeks) ? weeks.filter((week) => String(week || "").trim() !== "") : [];
}
const state = {
  view: "frequency",
  filters: { market: "", city: "", mso_type: "", head_end: "", crn_no: "", channel_name: "", band: "", week_from: "", week_to: "", change: "" },
  sortKey: "flow_order",
  sortDirection: "asc",
  page: 1,
  pageSize: 30,
};
const tableColumns = [
  { key: "market", label: "MARKET" },
  { key: "city", label: "CITY" },
  { key: "mso_type", label: "MSO TYPE" },
  { key: "head_end", label: "HEAD-END" },
  { key: "crn_no", label: "CRN No." },
  { key: "channel_name", label: "CHANNEL NAME" },
];
const filterOrder = ["market", "city", "mso_type", "head_end", "crn_no", "channel_name", "band", "week_from", "week_to", "change"];
const fieldMap = { market: "market", city: "city", mso_type: "mso_type", head_end: "head_end", crn_no: "crn_no", channel_name: "channel_name", band: "band" };
function getSingleSelectControl(id) {
  return {
    button: document.getElementById(id),
    menu: document.getElementById(`${id}Menu`),
    search: document.getElementById(`${id}Search`),
    options: document.getElementById(`${id}Options`),
  };
}
const filterPlaceholders = {
  market: "All Markets",
  city: "All Cities",
  mso_type: "All MSO Types",
  head_end: "All Headend",
  crn_no: "All CRN No",
  channel_name: "All Channels",
  band: "All Bands",
  week_from: "From Week",
  week_to: "To Week",
  change: "All Changes",
};
const filterSearchPlaceholders = {
  market: "Search market...",
  city: "Search city...",
  mso_type: "Search MSO type...",
  head_end: "Search headend...",
  crn_no: "Search CRN...",
  channel_name: "Search channel...",
  band: "Search band...",
  week_from: "Search week...",
  week_to: "Search week...",
  change: "Search change...",
};
const filters = {
  market: getSingleSelectControl("marketFilter"),
  city: getSingleSelectControl("cityFilter"),
  mso_type: getSingleSelectControl("msoTypeFilter"),
  head_end: getSingleSelectControl("headendFilter"),
  crn_no: getSingleSelectControl("crnFilter"),
  channel_name: getSingleSelectControl("channelFilter"),
  band: getSingleSelectControl("bandFilter"),
  week_from: getSingleSelectControl("weekFromFilter"),
  week_to: getSingleSelectControl("weekToFilter"),
  change: getSingleSelectControl("changeFilter"),
};
const viewButtons = {
  frequency: document.getElementById("frequencyViewButton"),
  rank: document.getElementById("rankViewButton"),
  band: document.getElementById("bandViewButton"),
};
const fullscreenButton = document.getElementById("fullscreenButton");
const exitFullscreenButton = document.getElementById("exitFullscreenButton");
const tableFullscreenScope = document.querySelector(".table1-scope");
const filterPanel = document.querySelector(".filter-panel");
const tablePanel = document.querySelector(".table-panel");
const tableWrap = document.querySelector(".table-wrap");
const fullscreenState = {
  active: false,
  usingNativeFullscreen: false,
  windowScrollY: 0,
  tableScrollTop: 0,
  tableScrollLeft: 0,
};
const DEFAULT_CHANNEL_REPORTS = __DEFAULT_CHANNEL_REPORTS__;
function sortSummaryChannels(channels) {
  const uniqueChannels = Array.from(new Set((channels || []).map((channel) => String(channel || "").trim()).filter(Boolean)));
  const indiaTv = uniqueChannels.find((channel) => formatChannelLabel(channel) === "INDIA TV");
  const otherChannels = uniqueChannels.filter((channel) => formatChannelLabel(channel) !== "INDIA TV");
  return [
    ...(indiaTv ? [indiaTv] : []),
    ...otherChannels.sort((left, right) => formatChannelLabel(left).localeCompare(formatChannelLabel(right))),
  ];
}
const channelReportState = {
  channel: "__default__",
  mso_type: "",
  week_from: "",
  week_to: "",
  open: false,
};
const channelReportControls = {
  channel: document.getElementById("channelReportChannelFilter"),
  mso_type: document.getElementById("channelReportMsoTypeFilter"),
  week_from: document.getElementById("channelReportWeekFromFilter"),
  week_to: document.getElementById("channelReportWeekToFilter"),
  container: document.getElementById("channelReportContainer"),
  count: document.getElementById("channelReportCount"),
  panel: document.querySelector(".channel-report-panel"),
  toggle: document.getElementById("channelReportToggleButton"),
  reset: document.getElementById("channelReportResetButton"),
  hide: document.getElementById("channelReportHideButton"),
};
const table1DownloadButton = document.getElementById("downloadTable1Button");
function formatNumber(value) { return new Intl.NumberFormat().format(value || 0); }
function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--" : date.toLocaleString("en-IN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
function createOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}
function populateOptionList(select, options, selectedValue) {
  const safeOptions = Array.isArray(options) ? options.filter((option) => option && String(option.value || "").trim() !== "") : [];
  const fallback = safeOptions.some((option) => option.value === selectedValue) ? selectedValue : (safeOptions[0]?.value || "");
  select.innerHTML = "";
  safeOptions.forEach((option) => select.appendChild(createOption(option.value, option.label)));
  select.value = fallback;
  return fallback;
}
function updateSingleSelectButton(control, value, placeholder, labels = null) {
  if (!control?.button) return;
  control.button.textContent = value ? (labels?.[value] || value) : placeholder;
}
function renderSingleSelectOptions(control, values, selectedValue, placeholder, onSelect, labels = null) {
  if (!control?.options) return;
  const safeValues = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "") : [];
  const query = String(control.search?.value || "").trim().toLowerCase();
  const fragment = document.createDocumentFragment();
  const options = [{ value: "", label: placeholder }, ...safeValues.map((value) => ({ value, label: labels?.[value] || value }))];
  options
    .filter((option) => !query || String(option.label || "").toLowerCase().includes(query))
    .forEach((option) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `filter-option-row${option.value === selectedValue ? " active" : ""}`;
      item.textContent = option.label;
      item.addEventListener("click", () => onSelect(option.value));
      fragment.appendChild(item);
    });
  control.options.replaceChildren(fragment);
}
function getConstrainedWeekOptions(key) {
  const weeks = normalizeWeeks(report.weeks || []);
  if (key === "week_from") {
    const toIndex = state.filters.week_to && weeks.includes(state.filters.week_to) ? weeks.indexOf(state.filters.week_to) : weeks.length - 1;
    return weeks.slice(0, toIndex + 1);
  }
  if (key === "week_to") {
    const fromIndex = state.filters.week_from && weeks.includes(state.filters.week_from) ? weeks.indexOf(state.filters.week_from) : 0;
    return weeks.slice(fromIndex);
  }
  return weeks;
}
function getControlOptions(key) {
  if (key === "week_from" || key === "week_to") return getConstrainedWeekOptions(key);
  return getOptions(key);
}
function closeSingleSelectMenus(exceptControl = null) {
  Object.values(filters).forEach((control) => {
    if (control !== exceptControl && control?.menu) control.menu.hidden = true;
  });
}
function syncSingleSelect(control, values, placeholder, selectedValue, onSelect, labels = null) {
  const safeValues = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "") : [];
  let fallback = selectedValue || "";
  if (fallback && !safeValues.includes(fallback)) {
    fallback = "";
  }
  updateSingleSelectButton(control, fallback, placeholder, labels);
  renderSingleSelectOptions(control, safeValues, fallback, placeholder, (value) => {
    onSelect(value);
    closeSingleSelectMenus();
  }, labels);
  return fallback;
}
function bindSingleSelect(control, key, onApply) {
  if (!control?.button) return;
  control.button.addEventListener("click", (event) => {
    event.stopPropagation();
    const next = control.menu?.hidden ?? false;
    closeSingleSelectMenus();
    if (control.menu) control.menu.hidden = !next;
    if (next && control.search) {
      control.search.value = "";
      control.search.dispatchEvent(new Event("input"));
      requestAnimationFrame(() => control.search?.focus());
    }
  });
  if (control.search) {
    control.search.placeholder = filterSearchPlaceholders[key] || "Search...";
    control.search.addEventListener("click", (event) => event.stopPropagation());
    control.search.addEventListener("input", () => {
      renderSingleSelectOptions(control, getControlOptions(key), state.filters[key], filterPlaceholders[key], onApply, key === "change" ? { Changed: "Changed", "No Change": "No Change" } : null);
    });
  }
}
function getVisibleWeeks() {
  const weeks = normalizeWeeks(report.weeks || []);
  if (!weeks.length) return [];
  if (state.filters.week_from || state.filters.week_to) {
    const fromIndex = state.filters.week_from && weeks.includes(state.filters.week_from) ? weeks.indexOf(state.filters.week_from) : 0;
    const toIndex = state.filters.week_to && weeks.includes(state.filters.week_to) ? weeks.indexOf(state.filters.week_to) : weeks.length - 1;
    const start = Math.min(fromIndex, toIndex);
    const end = Math.max(fromIndex, toIndex);
    return weeks.slice(start, end + 1);
  }
  return weeks.slice(Math.max(0, weeks.length - 4));
}
function formatChannelLabel(value) {
  return String(value || "").toUpperCase();
}
function getChannelReportWeekPair() {
  const allWeeks = normalizeWeeks(report.weeks || []);
  if (!allWeeks.length) return [];
  const fallbackTo = allWeeks[allWeeks.length - 1];
  const fallbackFrom = allWeeks[Math.max(0, allWeeks.length - 2)] || fallbackTo;
  const from = allWeeks.includes(channelReportState.week_from) ? channelReportState.week_from : fallbackFrom;
  const to = allWeeks.includes(channelReportState.week_to) ? channelReportState.week_to : fallbackTo;
  let fromIndex = allWeeks.indexOf(from);
  let toIndex = allWeeks.indexOf(to);
  if (fromIndex === toIndex && allWeeks.length > 1) {
    fromIndex = Math.max(0, toIndex - 1);
  }
  if (fromIndex > toIndex) {
    const swap = fromIndex;
    fromIndex = toIndex;
    toIndex = swap;
  }
  channelReportState.week_from = allWeeks[fromIndex];
  channelReportState.week_to = allWeeks[toIndex];
  return [allWeeks[fromIndex], allWeeks[toIndex]];
}
function syncChannelReportWeeksWithTable() {
  const allWeeks = normalizeWeeks(report.weeks || []);
  if (!allWeeks.length) return;
  if (state.filters.week_from && allWeeks.includes(state.filters.week_from)) {
    channelReportState.week_from = state.filters.week_from;
  }
  if (state.filters.week_to && allWeeks.includes(state.filters.week_to)) {
    channelReportState.week_to = state.filters.week_to;
  }
  if (!state.filters.week_from && !state.filters.week_to && !channelReportState.week_from && !channelReportState.week_to) {
    const fallbackTo = allWeeks[allWeeks.length - 1];
    const fallbackFrom = allWeeks[Math.max(0, allWeeks.length - 2)] || fallbackTo;
    channelReportState.week_from = fallbackFrom;
    channelReportState.week_to = fallbackTo;
  }
}
function getChannelReportSourceRecords() {
  return (report.records || []).filter((record) => {
    for (const [key, field] of Object.entries(fieldMap)) {
      if (key === "mso_type") continue;
      if (state.filters[key] && String(record[field] || "") !== state.filters[key]) return false;
    }
    if (channelReportState.mso_type) {
      if (String(record.mso_type || "") !== channelReportState.mso_type) return false;
    } else {
      if (String(record.mso_type || "").trim().toUpperCase() === "DTH") return false;
    }
    return true;
  });
}
function buildChannelReportOptions() {
  const channels = Array.from(
    new Set(
      getChannelReportSourceRecords()
        .map((record) => String(record.channel_name || "").trim())
        .filter(Boolean)
    )
  ).sort((left, right) => formatChannelLabel(left).localeCompare(formatChannelLabel(right)));
  return [
    { value: "__default__", label: "Default 4 Channels" },
    ...channels.map((channel) => ({ value: channel, label: formatChannelLabel(channel) })),
  ];
}
function getChannelReportTargets() {
  if (channelReportState.channel && channelReportState.channel !== "__default__") {
    return [channelReportState.channel];
  }
  const availableUpper = new Set(
    getChannelReportSourceRecords().map((record) => String(record.channel_name || "").trim().toUpperCase())
  );
  const matched = DEFAULT_CHANNEL_REPORTS.filter((channel) => availableUpper.has(channel.toUpperCase()));
  return sortSummaryChannels(matched.length ? matched : DEFAULT_CHANNEL_REPORTS);
}
let neighbourCache = new Map();
let neighbourCacheReportRef = null;

function getNeighbourForChannelInWeek(channelName, market, headend, week) {
  if (!channelName || !market || !headend || !week) return "";
  const sourceRecords = (typeof report !== "undefined" && report.records) ? report.records : [];
  if (!sourceRecords.length) return "";

  if (neighbourCacheReportRef !== sourceRecords) {
    neighbourCache.clear();
    neighbourCacheReportRef = sourceRecords;
  }

  const msoType = (channelReportState && channelReportState.mso_type)
    ? String(channelReportState.mso_type).trim().toUpperCase()
    : "";
  const cacheKey = `${channelName.toUpperCase()}||${market.trim()}||${headend.trim()}||${msoType}||${week}`;
  if (neighbourCache.has(cacheKey)) {
    return neighbourCache.get(cacheKey);
  }

  const headendRecords = sourceRecords.filter((r) => {
    if (String(r.market || "").trim() !== market) return false;
    if (String(r.head_end || "").trim() !== headend) return false;
    if (msoType) {
      if (String(r.mso_type || "").trim().toUpperCase() !== msoType) return false;
    } else {
      if (String(r.mso_type || "").trim().toUpperCase() === "DTH") return false;
    }
    return true;
  });

  if (!headendRecords.length) {
    neighbourCache.set(cacheKey, "");
    return "";
  }

  const sorted = headendRecords
    .filter((r) => r.frequencies?.[week] !== null && r.frequencies?.[week] !== undefined && r.frequencies?.[week] !== "" && String(r.frequencies?.[week]).toUpperCase() !== "NA")
    .sort((a, b) => Number(a.frequencies[week]) - Number(b.frequencies[week]));

  sorted.forEach((r, idx) => {
    const ch = String(r.channel_name || "").trim();
    let neighbour = "";
    if (idx > 0) {
      neighbour = String(sorted[idx - 1].channel_name || "").trim();
    } else if (idx + 1 < sorted.length) {
      neighbour = String(sorted[idx + 1].channel_name || "").trim();
    }
    const k = `${ch.toUpperCase()}||${market.trim()}||${headend.trim()}||${msoType}||${week}`;
    neighbourCache.set(k, neighbour);
  });

  return neighbourCache.get(cacheKey) || "";
}

let headendAvailCache = new Map();
let headendAvailReportRef = null;

function checkHeadendBecameAvailable(market, headend, previousWeek, currentWeek) {
  if (!market || !headend || !previousWeek || !currentWeek) return false;
  const sourceRecords = (typeof report !== "undefined" && report.records) ? report.records : [];
  if (!sourceRecords.length) return false;

  if (headendAvailReportRef !== sourceRecords) {
    headendAvailCache.clear();
    headendAvailReportRef = sourceRecords;
  }

  const msoType = (channelReportState && channelReportState.mso_type)
    ? String(channelReportState.mso_type).trim().toUpperCase()
    : "";
  const cacheKey = `${market.trim()}||${headend.trim()}||${msoType}||${previousWeek}||${currentWeek}`;
  if (headendAvailCache.has(cacheKey)) {
    return headendAvailCache.get(cacheKey);
  }

  const headendRecords = sourceRecords.filter((r) => {
    if (String(r.market || "").trim() !== market) return false;
    if (String(r.head_end || "").trim() !== headend) return false;
    if (msoType) {
      if (String(r.mso_type || "").trim().toUpperCase() !== msoType) return false;
    } else {
      if (String(r.mso_type || "").trim().toUpperCase() === "DTH") return false;
    }
    return true;
  });

  if (!headendRecords.length) {
    headendAvailCache.set(cacheKey, false);
    return false;
  }

  const prevHasData = headendRecords.some((r) => r.frequencies?.[previousWeek] !== null && r.frequencies?.[previousWeek] !== undefined && r.frequencies?.[previousWeek] !== "" && String(r.frequencies?.[previousWeek]).toUpperCase() !== "NA");
  const currHasData = headendRecords.some((r) => r.frequencies?.[currentWeek] !== null && r.frequencies?.[currentWeek] !== undefined && r.frequencies?.[currentWeek] !== "" && String(r.frequencies?.[currentWeek]).toUpperCase() !== "NA");
  const result = !prevHasData && currHasData;

  headendAvailCache.set(cacheKey, result);
  return result;
}

function buildChannelReportRows(channel, weeks) {
  const [previousWeek, currentWeek] = weeks;
  const grouped = new Map();
  getChannelReportSourceRecords().forEach((record) => {
    if (String(record.channel_name || "").trim().toUpperCase() !== String(channel || "").trim().toUpperCase()) return;
    const market = String(record.market || "").trim();
    const headend = String(record.head_end || "").trim();
    const key = `${market}||${headend}`;
    if (!grouped.has(key)) grouped.set(key, record);
  });
  return Array.from(grouped.values())
    .map((record) => {
      const previousFrequency = record.frequencies?.[previousWeek];
      const currentFrequency = record.frequencies?.[currentWeek];
      const previousRank = record.ranks?.[previousWeek];
      const currentRank = record.ranks?.[currentWeek];
      const previousMissing = previousFrequency === null || previousFrequency === undefined || previousFrequency === "" || String(previousFrequency).toUpperCase() === "NA";
      const currentMissing = currentFrequency === null || currentFrequency === undefined || currentFrequency === "" || String(currentFrequency).toUpperCase() === "NA";
      const hasFrequencyChange = previousMissing !== currentMissing || (!previousMissing && !currentMissing && String(previousFrequency) !== String(currentFrequency));

      const prevRankNum = Number(previousRank);
      const currRankNum = Number(currentRank);
      const prevRankValid = !isNaN(prevRankNum) && previousRank !== null && previousRank !== "" && String(previousRank).toUpperCase() !== "NA";
      const currRankValid = !isNaN(currRankNum) && currentRank !== null && currentRank !== "" && String(currentRank).toUpperCase() !== "NA";
      const hasRankChange = prevRankValid && currRankValid && prevRankNum !== currRankNum;

      const prevNeighbour = getNeighbourForChannelInWeek(channel, record.market, record.head_end, previousWeek);
      const currNeighbour = getNeighbourForChannelInWeek(channel, record.market, record.head_end, currentWeek);
      const prevNeighbourValid = prevNeighbour && prevNeighbour.toUpperCase() !== "NA";
      const currNeighbourValid = currNeighbour && currNeighbour.toUpperCase() !== "NA";
      const hasNeighbourChange = prevNeighbourValid && currNeighbourValid && prevNeighbour.toUpperCase() !== currNeighbour.toUpperCase();

      const hasAnyChange = hasFrequencyChange || hasRankChange || hasNeighbourChange;

      return {
        channel_name: record.channel_name,
        market: record.market,
        city: record.city,
        head_end: record.head_end,
        previousFrequency,
        currentFrequency,
        previousRank,
        currentRank,
        hasFrequencyChange,
        hasRankChange,
        hasNeighbourChange,
        hasAnyChange,
      };
    })
    .filter((record) => record.hasFrequencyChange)
    .sort((left, right) => {
      const marketCompare = String(left.market || "").localeCompare(String(right.market || ""));
      if (marketCompare !== 0) return marketCompare;
      return String(left.head_end || "").localeCompare(String(right.head_end || ""));
    });
}

function buildChannelReportNotes(channel, rows, weeks) {
  const channelName = formatChannelLabel(channel);
  if (!rows || !rows.length) {
    return [`${channelName} has no change`];
  }

  const [previousWeek, currentWeek] = weeks || [];
  const notes = [];

  rows.forEach((row) => {
    notes.push(buildChannelReportRemark(row, weeks));
  });

  return notes.length ? notes : [`${channelName} has no change`];
}

function formatExcelValue(value, fallback = "NA") {
  return value === null || value === undefined || value === "" ? fallback : value;
}
function isAllCitiesValue(value) {
  return String(value || "").trim().toUpperCase().replace(/\\s+/g, "") === "ALLCITIES";
}
function getFrequencyChangeStyle(previousValue, currentValue) {
  const previousMissing = previousValue === null || previousValue === undefined || previousValue === "";
  const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";
  if (previousMissing && currentMissing) return "neutral";
  if (previousMissing && !currentMissing) return "positive";
  if (!previousMissing && currentMissing) return "negative";
  if (Number(currentValue) > Number(previousValue)) return "positive";
  if (Number(currentValue) < Number(previousValue)) return "negative";
  return "neutral";
}
function getRankChangeStyle(previousValue, currentValue) {
  const previousMissing = previousValue === null || previousValue === undefined || previousValue === "";
  const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";
  if (previousMissing && currentMissing) return "neutral";
  if (previousMissing && !currentMissing) return "positive";
  if (!previousMissing && currentMissing) return "negative";
  if (Number(currentValue) < Number(previousValue)) return "positive";
  if (Number(currentValue) > Number(previousValue)) return "negative";
  return "neutral";
}
function getSequentialTrendStyle(weeks, values, index, styleResolver, emptyFallback = "neutral", filledFallback = "number") {
  const week = weeks[index];
  const currentValue = values?.[week];
  const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";
  if (index <= 0) {
    return currentMissing ? emptyFallback : filledFallback;
  }
  const previousValue = values?.[weeks[index - 1]];
  const style = styleResolver(previousValue, currentValue);
  return style === "neutral" && !currentMissing ? filledFallback : style;
}
function getChannelPlacementInWeek(channelName, market, headend, week) {
  if (!channelName || !market || !headend || !week) return "";
  const sourceRecords = (typeof report !== "undefined" && report.records) ? report.records : [];
  if (!sourceRecords.length) return "";

  const msoType = (channelReportState && channelReportState.mso_type)
    ? String(channelReportState.mso_type).trim().toUpperCase()
    : "";

  const headendRecords = sourceRecords.filter((r) => {
    if (String(r.market || "").trim() !== market) return false;
    if (String(r.head_end || "").trim() !== headend) return false;
    if (msoType) {
      if (String(r.mso_type || "").trim().toUpperCase() !== msoType) return false;
    } else {
      if (String(r.mso_type || "").trim().toUpperCase() === "DTH") return false;
    }
    return true;
  });

  if (!headendRecords.length) return "";

  const sorted = headendRecords
    .filter((r) => r.frequencies?.[week] !== null && r.frequencies?.[week] !== undefined && r.frequencies?.[week] !== "" && String(r.frequencies?.[week]).toUpperCase() !== "NA")
    .sort((a, b) => Number(a.frequencies[week]) - Number(b.frequencies[week]));

  const idx = sorted.findIndex((r) => String(r.channel_name || "").trim().toUpperCase() === String(channelName).trim().toUpperCase());
  const isSelf = String(channelName).trim().toUpperCase() === "INDIA TV";
  const selfRef = isSelf ? "us" : "it";
  if (idx < 0) return `no channel from the genre was placed beside ${selfRef}`;

  const prev = idx > 0 ? String(sorted[idx - 1].channel_name || "").trim() : "";
  const next = idx + 1 < sorted.length ? String(sorted[idx + 1].channel_name || "").trim() : "";

  if (prev && next) {
    return `between ${formatChannelLabel(prev)} & ${formatChannelLabel(next)}`;
  } else if (prev) {
    return `beside ${formatChannelLabel(prev)}`;
  } else if (next) {
    return `beside ${formatChannelLabel(next)}`;
  }
  return `no channel from the genre was placed beside ${selfRef}`;
}

function buildChannelReportRemark(row, weeks) {
  const channel = row.channel_name || "";
  const channelName = formatChannelLabel(channel);
  const isSelf = channelName === "INDIA TV";
  const selfRefCapital = isSelf ? "we are" : "it is";
  const [previousWeek, currentWeek] = weeks || [];

  const prevLcn = row.previousFrequency;
  const currLcn = row.currentFrequency;
  const prevRank = row.previousRank;
  const currRank = row.currentRank;

  const prevLcnMissing = prevLcn === null || prevLcn === undefined || prevLcn === "" || String(prevLcn).toUpperCase() === "NA";
  const currLcnMissing = currLcn === null || currLcn === undefined || currLcn === "" || String(currLcn).toUpperCase() === "NA";

  let remark = "";

  if (prevLcnMissing && !currLcnMissing) {
    remark = `${channelName}'s LCN became available (NA → ${currLcn})`;
  } else if (!prevLcnMissing && currLcnMissing) {
    remark = `${channelName} became unavailable (${prevLcn} → NA)`;
  } else if (!prevLcnMissing && !currLcnMissing && String(prevLcn) !== String(currLcn)) {
    remark = `${channelName}'s LCN has changed in this head end`;
  } else {
    remark = `${channelName} LCN remains ${currLcn}`;
  }

  const prevRankNum = Number(prevRank);
  const currRankNum = Number(currRank);
  const prevRankValid = !isNaN(prevRankNum) && prevRank !== null && prevRank !== "" && String(prevRank).toUpperCase() !== "NA";
  const currRankValid = !isNaN(currRankNum) && currRank !== null && currRank !== "" && String(currRank).toUpperCase() !== "NA";

  if (prevRankValid && currRankValid && prevRankNum !== currRankNum) {
    const rankVerb = currRankNum < prevRankNum ? "its rank improved" : "its rank dropped";
    remark += ` and ${rankVerb} from ${prevRank} to ${currRank}`;
  }

  const prevPlacement = getChannelPlacementInWeek(channel, row.market, row.head_end, previousWeek);
  const currPlacement = getChannelPlacementInWeek(channel, row.market, row.head_end, currentWeek);

  if (prevPlacement.startsWith("no channel")) {
    remark += `, previously ${prevPlacement}, now ${selfRefCapital} ${currPlacement}`;
  } else if (prevPlacement && prevPlacement !== currPlacement) {
    remark += `, previously it was placed ${prevPlacement}, now ${selfRefCapital} ${currPlacement}`;
  } else if (currPlacement) {
    remark += `, placed ${currPlacement}`;
  }

  return remark;
}
function exportTable1Excel() {
  syncChannelReportWeeksWithTable();
  const records = getFilteredRecords()
    .filter((record) => !isAllCitiesValue(record.city))
    .slice()
    .sort((left, right) => {
      const channelCompare = formatChannelLabel(left.channel_name || "").localeCompare(formatChannelLabel(right.channel_name || ""));
      if (channelCompare !== 0) return channelCompare;
      const marketCompare = String(left.market || "").localeCompare(String(right.market || ""));
      if (marketCompare !== 0) return marketCompare;
      const cityCompare = String(left.city || "").localeCompare(String(right.city || ""));
      if (cityCompare !== 0) return cityCompare;
      return String(left.head_end || "").localeCompare(String(right.head_end || ""));
    });
  const visibleWeeks = getVisibleWeeks();
  const activeWeeks = getChannelReportWeekPair();
  const targetChannels = ["INDIA TV", "AAJ TAK", "NEWS 18 INDIA", "REPUBLIC BHARAT"];
  const frequencyExportView = { series: "frequencies", changes: "changes" };
  const rankExportView = { series: "ranks", changes: "rank_changes" };
  const detailRows = [
    excelRow(["CHANNEL NAME", "MARKET", "CITY", "HEAD-END"], "header").concat(
      visibleWeeks.map((week) => excelCell(week, "header")),
      visibleWeeks.map((week) => excelCell(week, "header"))
    ),
  ];
  detailRows.unshift([
    excelCell("", "group", { mergeAcross: 3 }),
    excelCell("Freq", "group", { mergeAcross: Math.max(0, visibleWeeks.length - 1) }),
    excelCell("Rank", "group", { mergeAcross: Math.max(0, visibleWeeks.length - 1) }),
  ]);
  records.forEach((record) => {
    detailRows.push([
      excelCell(record.channel_name || "", "cell"),
      excelCell(record.market || "", "cell"),
      excelCell(record.city || "", "cell"),
      excelCell(record.head_end || "", "cell"),
      ...visibleWeeks.map((week, weekIndex) => {
        const value = record.frequencies?.[week];
        const status = getDisplayStatusForView(record, frequencyExportView, visibleWeeks, weekIndex, "frequency");
        const style = mapTableStatusToExcelStyle(status, value === null || value === undefined || value === "" ? "neutral" : "number");
        return excelCell(formatExcelValue(value, "NA"), style);
      }),
      ...visibleWeeks.map((week, weekIndex) => {
        const value = record.ranks?.[week];
        const status = getDisplayStatusForView(record, rankExportView, visibleWeeks, weekIndex, "rank");
        const style = mapTableStatusToExcelStyle(status, value === null || value === undefined || value === "" ? "neutral" : "number");
        return excelCell(formatExcelValue(value, "No Rank"), style);
      }),
    ]);
  });

  const reportRows = [
    [excelCell("Source: Chrome Track", "title", { mergeAcross: 7 })],
    [excelCell("Major Change", "meta", { mergeAcross: 7 })],
    blankExcelRow(8),
  ];

  targetChannels.forEach((channel) => {
    const rows = buildChannelReportRows(channel, activeWeeks).filter((row) => !isAllCitiesValue(row.city) && row.hasFrequencyChange);
    if (!rows.length) return;

    reportRows.push([
      excelCell("", "group", { mergeAcross: 2 }),
      excelCell("Freq", "group", { mergeAcross: 1 }),
      excelCell("Rank", "group", { mergeAcross: 1 }),
      excelCell("Remark", "group"),
    ]);
    reportRows.push([
      excelCell("CHANNEL NAME", "header"),
      excelCell("MARKET", "header"),
      excelCell("HEAD-END", "header"),
      excelCell(activeWeeks[0] || "Week 1", "header"),
      excelCell(activeWeeks[1] || "Week 2", "header"),
      excelCell(activeWeeks[0] || "Week 1", "header"),
      excelCell(activeWeeks[1] || "Week 2", "header"),
      excelCell("Remark", "header"),
    ]);

    rows.forEach((row) => {
      const currentFrequencyStyle = getFrequencyChangeStyle(row.previousFrequency, row.currentFrequency);
      const currentRankStyle = getRankChangeStyle(row.previousRank, row.currentRank);
      const currentFrequencyExportStyle = currentFrequencyStyle === "neutral"
        ? (row.currentFrequency === null || row.currentFrequency === undefined || row.currentFrequency === "" ? "neutral" : "number")
        : currentFrequencyStyle;
      const currentRankExportStyle = currentRankStyle === "neutral"
        ? (row.currentRank === null || row.currentRank === undefined || row.currentRank === "" ? "neutral" : "number")
        : currentRankStyle;

      const remarkText = buildChannelReportRemark(row, activeWeeks);

      reportRows.push([
        excelCell(formatChannelLabel(row.channel_name), "cell"),
        excelCell(row.market || "", "cell"),
        excelCell(row.head_end || "", "cell"),
        excelCell(formatExcelValue(row.previousFrequency, "NA"), row.previousFrequency === null || row.previousFrequency === undefined || row.previousFrequency === "" ? "neutral" : "number"),
        excelCell(formatExcelValue(row.currentFrequency, "NA"), currentFrequencyExportStyle),
        excelCell(formatExcelValue(row.previousRank, "No Rank"), row.previousRank === null || row.previousRank === undefined || row.previousRank === "" ? "neutral" : "number"),
        excelCell(formatExcelValue(row.currentRank, "No Rank"), currentRankExportStyle),
        excelCell(remarkText, "textWrap"),
      ]);
    });

    reportRows.push(blankExcelRow(8));
  });

  if (reportRows.length === 3) {
    reportRows.push([excelCell("No frequency changes found for the selected channels and weeks.", "textWrap", { mergeAcross: 7 })]);
  }

  downloadExcelWorkbook(`table1_${getActiveBaseView()}_export`, [
    {
      name: "Summary Sheet",
      columns: [180, 180, 260, 90, 90, 90, 90, 420],
      rows: reportRows,
    },
    {
      name: "Detailed Sheet",
      columns: [180, 170, 140, 240, ...visibleWeeks.map(() => 85), ...visibleWeeks.map(() => 85)],
      rows: detailRows,
    },
  ]);
}
function getChannelReportMsoTypes() {
  const msoTypes = new Set();
  (report.records || []).forEach((record) => {
    const value = String(record.mso_type || "").trim();
    if (value) msoTypes.add(value);
  });
  return Array.from(msoTypes).sort((a, b) => a.localeCompare(b));
}
function renderChannelReports() {
  if (channelReportControls.panel) {
    channelReportControls.panel.hidden = !channelReportState.open;
  }
  if (channelReportControls.toggle) {
    channelReportControls.toggle.textContent = channelReportState.open ? "Hide Report" : "Show Report";
  }
  if (!channelReportState.open) return;
  const container = channelReportControls.container;
  if (!container) return;
  syncChannelReportWeeksWithTable();
  const weeks = getChannelReportWeekPair();
  const allWeeks = normalizeWeeks(report.weeks || []);
  channelReportState.channel = populateOptionList(channelReportControls.channel, buildChannelReportOptions(), channelReportState.channel || "__default__");
  channelReportState.mso_type = populateSelect(channelReportControls.mso_type, getChannelReportMsoTypes(), "All MSO Types", channelReportState.mso_type);
  channelReportState.week_from = populateSelect(channelReportControls.week_from, allWeeks, "From Week", channelReportState.week_from);
  channelReportState.week_to = populateSelect(channelReportControls.week_to, allWeeks, "To Week", channelReportState.week_to);
  const activeWeeks = getChannelReportWeekPair();
  const channels = getChannelReportTargets();
  channelReportControls.count.textContent = `${channels.length} channel${channels.length === 1 ? "" : "s"}`;
  const fragment = document.createDocumentFragment();
  if (!channels.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No channel report data available.";
    container.replaceChildren(empty);
    return;
  }
  channels.forEach((channel) => {
    const rows = buildChannelReportRows(channel, activeWeeks);
    const notes = buildChannelReportNotes(channel, rows, activeWeeks);
    const card = document.createElement("section");
    card.className = "channel-report-card";

    const header = document.createElement("div");
    header.className = "channel-report-card-header";
    const title = document.createElement("h3");
    title.textContent = formatChannelLabel(channel);
    header.appendChild(title);
    card.appendChild(header);

    const wrap = document.createElement("div");
    wrap.className = "channel-report-table-wrap";
    const table = document.createElement("table");
    table.className = "channel-report-table";
    const thead = document.createElement("thead");

    const groupRow = document.createElement("tr");
    [
      { text: "CHANNEL NAME", rowSpan: 2 },
      { text: "MARKET", rowSpan: 2 },
      { text: "HEAD-END", rowSpan: 2 },
    ].forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.text;
      th.rowSpan = column.rowSpan;
      th.className = "channel-report-subhead";
      groupRow.appendChild(th);
    });
    [
      { text: "Freq", colSpan: activeWeeks.length },
      { text: "Rank", colSpan: activeWeeks.length },
    ].forEach((group) => {
      const th = document.createElement("th");
      th.textContent = group.text;
      th.colSpan = Math.max(group.colSpan, 1);
      th.className = "channel-report-group-head";
      groupRow.appendChild(th);
    });

    const weekRow = document.createElement("tr");
    [...activeWeeks, ...activeWeeks].forEach((week, index, allWeeks) => {
      const th = document.createElement("th");
      th.textContent = week;
      const weekGroupLength = Math.max(activeWeeks.length, 1);
      const weekIndex = index % weekGroupLength;
      th.className = `channel-report-subhead${weekIndex === 0 ? " channel-report-group-start" : ""}${weekIndex === weekGroupLength - 1 ? " channel-report-group-end" : ""}`;
      weekRow.appendChild(th);
    });
    thead.append(groupRow, weekRow);

    const tbody = document.createElement("tbody");
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3 + activeWeeks.length * 2;
      td.className = "empty-state";
      td.textContent = "No frequency changes found for the selected weeks.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        [row.channel_name, row.market, row.head_end].forEach((value, index) => {
          const td = document.createElement("td");
          td.textContent = value === row.channel_name ? String(value || "").toUpperCase() : (value || "");
          td.className = index === 2 ? "channel-report-leading-end" : "channel-report-leading";
          tr.appendChild(td);
        });
        [
          { previous: row.previousFrequency, current: row.currentFrequency },
          { previous: row.previousRank, current: row.currentRank },
        ].forEach((pair, pairIndex) => {
          [pair.previous, pair.current].forEach((value, index) => {
            const td = document.createElement("td");
            td.textContent = value === null || value === undefined || value === "" ? "NA" : String(value);
            const boundaryClass = `${index === 0 ? " channel-report-group-start" : ""}${index === 1 ? " channel-report-group-end" : ""}`;
            td.className = `channel-report-cell-stable${boundaryClass}${pairIndex === 0 ? " channel-report-freq-cell" : " channel-report-rank-cell"}`;
            if (value === null || value === undefined || value === "") td.className = `channel-report-cell-missing${boundaryClass}${pairIndex === 0 ? " channel-report-freq-cell" : " channel-report-rank-cell"}`;
            if (index === 1 && pair.previous !== pair.current && value !== null && value !== undefined && value !== "") {
              const currentNumber = Number(value);
              const previousNumber = Number(pair.previous);
              if (!Number.isNaN(currentNumber) && !Number.isNaN(previousNumber)) {
                td.className = `${currentNumber > previousNumber ? "channel-report-cell-increase" : "channel-report-cell-decrease"}${boundaryClass}${pairIndex === 0 ? " channel-report-freq-cell" : " channel-report-rank-cell"}`;
              }
            }
            tr.appendChild(td);
          });
        });
        tbody.appendChild(tr);
      });
    }
    table.append(thead, tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);

    const notesList = document.createElement("ul");
    notesList.className = "channel-report-notes";
    notes.forEach((note) => {
      const item = document.createElement("li");
      item.textContent = note;
      notesList.appendChild(item);
    });
    card.appendChild(notesList);
    fragment.appendChild(card);
  });
  container.replaceChildren(fragment);
}
function resetChannelReports() {
  channelReportState.channel = "__default__";
  channelReportState.mso_type = "";
  channelReportState.week_from = "";
  channelReportState.week_to = "";
  renderChannelReports();
}
function getActiveBaseView() {
  return state.view === "report" ? "frequency" : state.view;
}
function isMissingValue(value) {
  return value === null || value === undefined || value === "";
}
function getDisplayStatusForView(record, viewConfig, weeks, weekIndex, activeView) {
  if (weekIndex === 0) return "baseline";
  const week = weeks[weekIndex];
  const previousWeek = weeks[weekIndex - 1];
  const currentValue = record[viewConfig.series]?.[week];
  const previousValue = record[viewConfig.series]?.[previousWeek];
  const currentMissing = isMissingValue(currentValue);
  const previousMissing = isMissingValue(previousValue);
  if (previousMissing && currentMissing) return "no_change";
  if (previousMissing && !currentMissing) {
    return activeView === "rank" ? "improve" : "increase";
  }
  if (!previousMissing && currentMissing) {
    return activeView === "rank" ? "decline" : "decrease";
  }
  if (currentMissing) return "missing";
  return record[viewConfig.changes]?.[week] || "no_change";
}
function getDisplayStatus(record, viewConfig, weeks, weekIndex) {
  return getDisplayStatusForView(record, viewConfig, weeks, weekIndex, state.view);
}
function mapTableStatusToExcelStyle(status, fallback = "number") {
  if (status === "increase" || status === "improve") return "positive";
  if (status === "decrease" || status === "decline") return "negative";
  if (status === "change") return "highlight";
  if (status === "missing") return "missing";
  if (status === "no_change") return fallback;
  if (status === "baseline") return fallback;
  return fallback;
}
function isChangedStatus(status) {
  return ["increase", "decrease", "improve", "decline", "change"].includes(status);
}
function hasVisibleChange(record, viewConfig, weeks) {
  if (weeks.length <= 1) return false;
  return weeks.slice(1).some((_week, index) => isChangedStatus(getDisplayStatus(record, viewConfig, weeks, index + 1)));
}
function getViewConfig() {
  const activeView = getActiveBaseView();
  if (activeView === "rank") return { series: "ranks", changes: "rank_changes", status: "rank_change_status", positive: "improve", negative: "decline", kpiOne: "Rank Improved", kpiTwo: "Rank Declined", title: "Weekly Rank Analysis" };
  if (activeView === "band") return { series: "bands", changes: "band_changes", status: "band_change_status", positive: "change", negative: "no_change", kpiOne: "Band Changed", kpiTwo: "Band Stable", title: "Weekly Band Analysis" };
  return { series: "frequencies", changes: "changes", status: "change_status", positive: "increase", negative: "decrease", kpiOne: "Frequency Increased", kpiTwo: "Frequency Decreased", title: "Weekly Frequency Analysis" };
}
function filterRecords(ignoreKey = "") {
  const viewConfig = getViewConfig();
  const visibleWeeks = getVisibleWeeks();
  return report.records.filter((record) => {
    for (const [key, field] of Object.entries(fieldMap)) {
      if (key === ignoreKey) continue;
      if (key === "mso_type") continue;
      if (state.filters[key] && String(record[field] || "") !== state.filters[key]) return false;
    }
    if (ignoreKey !== "mso_type") {
      if (state.filters.mso_type) {
        if (String(record.mso_type || "") !== state.filters.mso_type) return false;
      } else {
        if (String(record.mso_type || "").trim().toUpperCase() === "DTH") return false;
      }
    }
    if (ignoreKey !== "change" && state.filters.change) {
      if (state.filters.change === "Changed") {
        if (!hasVisibleChange(record, viewConfig, visibleWeeks)) {
          return false;
        }
      }
      if (state.filters.change === "No Change") {
        if (hasVisibleChange(record, viewConfig, visibleWeeks)) {
          return false;
        }
      }
    }
    return true;
  });
}
function getFilteredRecords() {
  return filterRecords();
}
function getOptions(key) {
  if (key === "week_from" || key === "week_to") return getConstrainedWeekOptions(key);
  if (key === "change") return ["Changed", "No Change"];
  const field = fieldMap[key];
  if (!field) return [];
  const values = new Set();
  const records = filterRecords(key);
  records.forEach((record) => {
    const value = String(record[field] || "").trim();
    if (value) values.add(value);
  });
  return Array.from(values).sort((a, b) => a.localeCompare(b));
}
function populateSelect(select, values, allLabel, selectedValue) {
  const safeValues = values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  if (selectedValue && !safeValues.includes(selectedValue)) {
    safeValues.push(selectedValue);
    safeValues.sort((a, b) => String(a).localeCompare(String(b)));
  }
  if (select instanceof HTMLSelectElement) {
    const safeSelectedValue = selectedValue || "";
    select.innerHTML = "";
    select.appendChild(createOption("", allLabel));
    safeValues.forEach((value) => select.appendChild(createOption(value, value)));
    select.value = safeSelectedValue;
    return safeSelectedValue;
  }
  const safeSelectedValue = selectedValue || "";
  return syncSingleSelect(select, safeValues, allLabel, safeSelectedValue, () => {}, null);
}
function applyFilterValue(key, value) {
  state.filters[key] = value;
  if (key === "week_from" || key === "week_to") {
    const weeks = normalizeWeeks(report.weeks || []);
    const fromIndex = state.filters.week_from && weeks.includes(state.filters.week_from) ? weeks.indexOf(state.filters.week_from) : -1;
    const toIndex = state.filters.week_to && weeks.includes(state.filters.week_to) ? weeks.indexOf(state.filters.week_to) : -1;
    if (fromIndex >= 0 && toIndex >= 0 && fromIndex > toIndex) {
      if (key === "week_from") state.filters.week_to = state.filters.week_from;
      else state.filters.week_from = state.filters.week_to;
    }
  }
  if (key === "week_from" && value) {
    state.filters.week_to = state.filters.week_to && getConstrainedWeekOptions("week_to").includes(state.filters.week_to) ? state.filters.week_to : value;
  }
  if (key === "week_to" && value) {
    state.filters.week_from = state.filters.week_from && getConstrainedWeekOptions("week_from").includes(state.filters.week_from) ? state.filters.week_from : value;
  }
  state.page = 1;
  render();
}
function syncFilters() {
  state.filters.market = syncSingleSelect(filters.market, getOptions("market"), "All Markets", state.filters.market, (value) => applyFilterValue("market", value), null);
  state.filters.city = syncSingleSelect(filters.city, getOptions("city"), "All Cities", state.filters.city, (value) => applyFilterValue("city", value), null);
  state.filters.mso_type = syncSingleSelect(filters.mso_type, getOptions("mso_type"), "All MSO Types", state.filters.mso_type, (value) => applyFilterValue("mso_type", value), null);
  state.filters.head_end = syncSingleSelect(filters.head_end, getOptions("head_end"), "All Headend", state.filters.head_end, (value) => applyFilterValue("head_end", value), null);
  state.filters.crn_no = syncSingleSelect(filters.crn_no, getOptions("crn_no"), "All CRN No", state.filters.crn_no, (value) => applyFilterValue("crn_no", value), null);
  state.filters.channel_name = syncSingleSelect(filters.channel_name, getOptions("channel_name"), "All Channels", state.filters.channel_name, (value) => applyFilterValue("channel_name", value), null);
  state.filters.band = syncSingleSelect(filters.band, getOptions("band"), "All Bands", state.filters.band, (value) => applyFilterValue("band", value), null);
  state.filters.week_from = syncSingleSelect(filters.week_from, getOptions("week_from"), "From Week", state.filters.week_from, (value) => applyFilterValue("week_from", value), null);
  state.filters.week_to = syncSingleSelect(filters.week_to, getOptions("week_to"), "To Week", state.filters.week_to, (value) => applyFilterValue("week_to", value), null);
  state.filters.change = syncSingleSelect(filters.change, getOptions("change"), "All Changes", state.filters.change, (value) => applyFilterValue("change", value), { Changed: "Changed", "No Change": "No Change" });
}
function sortValue(record, sortKey, weeks) {
  if (sortKey === "flow_order") {
    return [0, [
      String(record.market || "").toLowerCase(),
      String(record.city || "").toLowerCase(),
      String(record.head_end || "").toLowerCase(),
      String(record.channel_name || "").toLowerCase(),
    ]];
  }
  const viewConfig = getViewConfig();
  let value = record[sortKey];
  if (value === undefined && weeks.includes(sortKey)) value = record[viewConfig.series][sortKey];
  if (value === null || value === undefined || value === "") return [1, ""];
  if (typeof value === "number") return [0, value];
  return [0, String(value).toLowerCase()];
}
function getFilteredRecords() {
  const visibleWeeks = getVisibleWeeks();
  const items = filterRecords();
  const sorted = items.slice().sort((a, b) => {
    const left = sortValue(a, state.sortKey, visibleWeeks);
    const right = sortValue(b, state.sortKey, visibleWeeks);
    if (left[0] !== right[0]) return left[0] - right[0];
    if (left[1] < right[1]) return state.sortDirection === "asc" ? -1 : 1;
    if (left[1] > right[1]) return state.sortDirection === "asc" ? 1 : -1;
    return 0;
  });
  return sorted;
}
function getReportWeeks() {
  const visibleWeeks = getVisibleWeeks();
  return visibleWeeks.length > 2 ? visibleWeeks.slice(-2) : visibleWeeks.slice();
}
function getReportChannel(records) {
  const selectedChannel = String(state.filters.channel_name || "").trim();
  if (selectedChannel) return selectedChannel;
  const channels = Array.from(
    new Set(
      records
        .map((record) => String(record.channel_name || "").trim())
        .filter(Boolean)
    )
  ).sort((left, right) => left.localeCompare(right));
  return channels[0] || "";
}
function getReportRows(records) {
  const channel = getReportChannel(records);
  const reportWeeks = getReportWeeks();
  const rows = records.filter((record) => String(record.channel_name || "").trim() === channel);
  return { channel, weeks: reportWeeks, rows };
}
function buildReportNotes(rows, weeks, channel) {
  if (!channel) {
    return ["Select a channel in the Channel filter to view the report."];
  }
  if (weeks.length < 2) {
    return [`${channel} report needs at least two visible weeks.`];
  }
  return buildChannelReportNotes(channel, rows, weeks);
}
function buildTableHead() {
  const tableHead = document.getElementById("tableHead");
  if (state.view === "report") {
    const reportData = getReportRows(getFilteredRecords());
    const titleRow = document.createElement("tr");
    const titleHead = document.createElement("th");
    titleHead.colSpan = 3 + reportData.weeks.length * 2;
    titleHead.textContent = reportData.channel || "Channel Report";
    titleHead.className = "report-channel-title";
    titleRow.appendChild(titleHead);

    const groupRow = document.createElement("tr");
    const leadingColumns = [
      { label: "CHANNEL NAME", rowSpan: 2 },
      { label: "MARKET", rowSpan: 2 },
      { label: "HEAD-END", rowSpan: 2 },
    ];
    leadingColumns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.label;
      th.rowSpan = column.rowSpan;
      th.className = "report-subhead";
      groupRow.appendChild(th);
    });
    [
      { label: "Freq", span: reportData.weeks.length },
      { label: "Rank", span: reportData.weeks.length },
    ].forEach((group) => {
      const th = document.createElement("th");
      th.textContent = group.label;
      th.colSpan = Math.max(group.span, 1);
      th.className = "report-group-head";
      groupRow.appendChild(th);
    });

    const weekRow = document.createElement("tr");
    [...reportData.weeks, ...reportData.weeks].forEach((week, index) => {
      const th = document.createElement("th");
      th.textContent = week;
      const weekGroupLength = Math.max(reportData.weeks.length, 1);
      const weekIndex = index % weekGroupLength;
      th.className = `report-subhead${weekIndex === 0 ? " report-group-start" : ""}${weekIndex === weekGroupLength - 1 ? " report-group-end" : ""}`;
      weekRow.appendChild(th);
    });
    tableHead.replaceChildren(titleRow, groupRow, weekRow);
    return;
  }
  const tr = document.createElement("tr");
  [...tableColumns, ...getVisibleWeeks().map((week) => ({ key: week, label: week })), { key: "change_status", label: "CHANGE" }].forEach((column) => {
    const th = document.createElement("th");
    const isActive = state.sortKey === column.key;
    const suffix = isActive ? (state.sortDirection === "asc" ? " ^" : " v") : "";
    th.textContent = `${column.label}${suffix}`;
    th.className = "sortable";
    th.addEventListener("click", () => {
      if (state.sortKey === column.key) state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
      else { state.sortKey = column.key; state.sortDirection = "asc"; }
      render();
    });
    tr.appendChild(th);
  });
  tableHead.replaceChildren(tr);
}
function formatWeekValue(value, status, isBaseline) {
  if (value === null || value === undefined || value === "") return "NA";
  if (isBaseline || status === "baseline" || status === "missing" || status === "no_change") return String(value);
  if (state.view === "rank") {
    if (status === "improve") return `+ ${value}`;
    if (status === "decline") return `- ${value}`;
    return String(value);
  }
  if (state.view === "band") {
    if (status === "change") return `* ${value}`;
    return String(value);
  }
  if (status === "increase") return `+ ${value}`;
  if (status === "decrease") return `- ${value}`;
  return String(value);
}
function renderFocusSummary(records) {
  const container = document.getElementById("focusSummary");
  if (!container) return;
  if (state.view === "report") {
    const reportData = getReportRows(records);
    const notes = buildReportNotes(reportData.rows, reportData.weeks, reportData.channel);
    container.innerHTML = `<ul class="report-notes">${notes.map((note) => `<li>${note}</li>`).join("")}</ul>`;
    return;
  }
  const labels = { "INDIA TV": "India TV", "AAJ TAK": "Aaj Tak", "NEWS 18 INDIA": "News 18", "REPUBLIC BHARAT": "Republic Bharat" };
  const viewConfig = getViewConfig();
  const visibleWeeks = getVisibleWeeks();
  const items = Object.entries(labels).map(([channel, label]) => {
    const selected = records.filter((record) => String(record.channel_name || "").toUpperCase() === channel);
    if (!selected.length) return "";
    let positive = 0, negative = 0, noChange = 0, latestPositive = 0, latestNegative = 0;
    const latestWeek = visibleWeeks[visibleWeeks.length - 1];
    selected.forEach((record) => {
      visibleWeeks.slice(1).forEach((week, index) => {
        const status = getDisplayStatus(record, viewConfig, visibleWeeks, index + 1);
        if (status === viewConfig.positive) positive += 1;
        else if (status === viewConfig.negative) negative += 1;
        else if (status === "increase") positive += 1;
        else if (status === "decrease") negative += 1;
        else if (status === "no_change") noChange += 1;
      });
      const latestStatus = getDisplayStatus(record, viewConfig, visibleWeeks, visibleWeeks.length - 1);
      if (latestStatus === viewConfig.positive) latestPositive += 1;
      else if (latestStatus === viewConfig.negative) latestNegative += 1;
      else if (latestStatus === "increase") latestPositive += 1;
      else if (latestStatus === "decrease") latestNegative += 1;
    });
    const positiveLabel = state.view === "rank" ? "improved" : state.view === "band" ? "changed" : "increased";
    const negativeLabel = state.view === "rank" ? "declined" : state.view === "band" ? "stable" : "decreased";
    const latestText = latestPositive || latestNegative ? ` Latest: ${latestPositive ? `${formatNumber(latestPositive)} ${positiveLabel}` : ""}${latestPositive && latestNegative ? ", " : ""}${latestNegative ? `${formatNumber(latestNegative)} ${negativeLabel}` : ""} in ${latestWeek}.` : "";
    return `<div class="focus-line"><strong>${label}</strong><span>${formatNumber(selected.length)} rows, ${formatNumber(positive)} ${positiveLabel}, ${formatNumber(negative)} ${negativeLabel}, ${formatNumber(noChange)} stable.${latestText}</span></div>`;
  }).filter(Boolean).join("");
  container.innerHTML = items || '<div class="focus-line">No channel summary available for the current filters.</div>';
}
function renderTable(records) {
  const tableBody = document.getElementById("tableBody");
  if (state.view === "report") {
    const reportData = getReportRows(records);
    const totalPages = Math.max(1, Math.ceil(reportData.rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * state.pageSize;
    const pageItems = reportData.rows.slice(start, start + state.pageSize);
    if (!pageItems.length) {
      tableBody.replaceChildren(document.getElementById("emptyStateTemplate").content.cloneNode(true));
      return;
    }
    const [previousWeek, currentWeek] = reportData.weeks;
    const fragment = document.createDocumentFragment();
    pageItems.forEach((record) => {
      const tr = document.createElement("tr");
      [
        record.channel_name,
        record.market,
        record.head_end,
      ].forEach((value, index) => {
        const td = document.createElement("td");
        td.textContent = value || "";
        td.className = index === 2 ? "report-leading-end" : "report-leading";
        tr.appendChild(td);
      });
      reportData.weeks.forEach((week, weekIndex) => {
        const td = document.createElement("td");
        const value = record.frequencies?.[week];
        td.textContent = value === null || value === undefined || value === "" ? "NA" : String(value);
        const boundaryClass = `${weekIndex === 0 ? " report-group-start" : ""}${weekIndex === reportData.weeks.length - 1 ? " report-group-end" : ""}`;
        td.className = `report-cell-neutral report-freq-cell${boundaryClass}`;
        if (value === null || value === undefined || value === "") td.className = `report-cell-missing report-freq-cell${boundaryClass}`;
        if (week === currentWeek && previousWeek && record.frequencies?.[previousWeek] !== value && value !== null && value !== undefined && value !== "") td.className = `report-cell-latest report-freq-cell${boundaryClass}`;
        tr.appendChild(td);
      });
      reportData.weeks.forEach((week, weekIndex) => {
        const td = document.createElement("td");
        const value = record.ranks?.[week];
        td.textContent = value === null || value === undefined || value === "" ? "NA" : String(value);
        const boundaryClass = `${weekIndex === 0 ? " report-group-start" : ""}${weekIndex === reportData.weeks.length - 1 ? " report-group-end" : ""}`;
        td.className = `report-cell-neutral report-rank-cell${boundaryClass}`;
        if (value === null || value === undefined || value === "") td.className = `report-cell-missing report-rank-cell${boundaryClass}`;
        if (week === currentWeek && previousWeek && record.ranks?.[previousWeek] !== value && value !== null && value !== undefined && value !== "") td.className = `report-cell-latest report-rank-cell${boundaryClass}`;
        tr.appendChild(td);
      });
      fragment.appendChild(tr);
    });
    tableBody.replaceChildren(fragment);
    return;
  }
  const visibleWeeks = getVisibleWeeks();
  const start = (state.page - 1) * state.pageSize;
  const pageItems = records.slice(start, start + state.pageSize);
  if (!pageItems.length) {
    tableBody.replaceChildren(document.getElementById("emptyStateTemplate").content.cloneNode(true));
    return;
  }
  const viewConfig = getViewConfig();
  const fragment = document.createDocumentFragment();
  pageItems.forEach((record) => {
    const tr = document.createElement("tr");
    tableColumns.forEach((column) => {
      const td = document.createElement("td");
      td.textContent = record[column.key] ?? "";
      tr.appendChild(td);
    });
    visibleWeeks.forEach((week, index) => {
      const td = document.createElement("td");
      const value = record[viewConfig.series][week];
      const status = getDisplayStatus(record, viewConfig, visibleWeeks, index);
      const textVal = formatWeekValue(value, status, index === 0);
      td.textContent = textVal;
      td.classList.add(`status-${status}`);
      if (status === "missing" || textVal === "NA" || value === null || value === undefined || value === "") {
        td.classList.add("cell-na");
        td.classList.add("status-missing");
      }
      tr.appendChild(td);
    });
    const changeTd = document.createElement("td");
    changeTd.textContent = hasVisibleChange(record, viewConfig, visibleWeeks) ? "YES" : "NO";
    changeTd.classList.add(changeTd.textContent === "NO" ? "change-no" : "change-yes");
    tr.appendChild(changeTd);
    fragment.appendChild(tr);
  });
  tableBody.replaceChildren(fragment);
}
function updateKpis(records) {
  const countDistinct = (key) => new Set(
    records
      .map((record) => String(record[key] ?? "").trim())
      .filter(Boolean)
  ).size;
  document.getElementById("kpiTotalRows").textContent = formatNumber(records.length);
  document.getElementById("kpiTotalMarket").textContent = formatNumber(countDistinct("market"));
  document.getElementById("kpiTotalCity").textContent = formatNumber(countDistinct("city"));
  document.getElementById("kpiTotalMsoType").textContent = formatNumber(countDistinct("mso_type"));
  document.getElementById("kpiTotalHeadend").textContent = formatNumber(countDistinct("head_end"));
  document.getElementById("kpiTotalChannel").textContent = formatNumber(countDistinct("channel_name"));
  document.getElementById("kpiTotalBand").textContent = formatNumber(countDistinct("band"));
}
function getPageSize() {
  if (!fullscreenState.active) return 30;
  const viewportHeight = window.innerHeight || 900;
  return Math.max(45, Math.floor((viewportHeight - 230) / 26));
}
function downloadStandaloneDashboard() {
  const embeddedBundle = JSON.stringify(window.__CHROME_REPORT_DATA__ || reportBundle || {}).split("</").join("<\\/");
  const sourceTag = '<scr' + 'ipt src="./frequency_report.json"><\\/scr' + 'ipt>';
  const embeddedTag = '<scr' + 'ipt>window.__CHROME_REPORT_DATA__ = ' + embeddedBundle + ';<\\/scr' + 'ipt>';
  const html = `<!DOCTYPE html>\n${document.documentElement.outerHTML}`
    .replace(sourceTag, embeddedTag);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "chrome_report_dashboard.html";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
function syncFullscreenButtons() {
  const label = fullscreenState.active ? "Exit Full Screen" : "Full Screen";
  fullscreenButton.textContent = label;
  if (exitFullscreenButton) exitFullscreenButton.hidden = !fullscreenState.active;
}
function setFullscreen(active) {
  if (!tableFullscreenScope || !tableWrap || fullscreenState.active === active) return;
  if (active) {
    fullscreenState.windowScrollY = window.scrollY || window.pageYOffset || 0;
    fullscreenState.tableScrollTop = tableWrap.scrollTop;
    fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
    fullscreenState.active = true;
    document.body.classList.add("table-fullscreen-active");
    tableFullscreenScope.classList.add("table1-scope-fullscreen");
    filterPanel?.classList.add("table1-scope-child");
    tablePanel?.classList.add("table1-scope-child");
    state.pageSize = getPageSize();
    state.page = 1;
    render();
    requestAnimationFrame(() => {
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
    });
  } else {
    fullscreenState.tableScrollTop = tableWrap.scrollTop;
    fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
    fullscreenState.active = false;
    document.body.classList.remove("table-fullscreen-active");
    tableFullscreenScope.classList.remove("table1-scope-fullscreen");
    filterPanel?.classList.remove("table1-scope-child");
    tablePanel?.classList.remove("table1-scope-child");
    state.pageSize = getPageSize();
    state.page = 1;
    render();
    requestAnimationFrame(() => {
      window.scrollTo({ top: fullscreenState.windowScrollY, behavior: "auto" });
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
    });
  }
  syncFullscreenButtons();
}
async function enterNativeFullscreen() {
  if (!tableFullscreenScope?.requestFullscreen) return false;
  try {
    fullscreenState.usingNativeFullscreen = true;
    await tableFullscreenScope.requestFullscreen();
    return true;
  } catch (error) {
    fullscreenState.usingNativeFullscreen = false;
    return false;
  }
}
async function exitNativeFullscreen() {
  if (!document.fullscreenElement) return false;
  try {
    await document.exitFullscreen();
    return true;
  } catch (error) {
    return false;
  }
}
async function toggleFullscreen() {
  if (fullscreenState.active) {
    if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === tableFullscreenScope) {
      const exited = await exitNativeFullscreen();
      if (!exited) {
        fullscreenState.usingNativeFullscreen = false;
        setFullscreen(false);
      }
      return;
    }
    setFullscreen(false);
    return;
  }
  const entered = await enterNativeFullscreen();
  if (!entered) {
    fullscreenState.usingNativeFullscreen = false;
    setFullscreen(true);
  }
}
function render() {
  syncFilters();
  renderChannelReports();
  const visibleWeeks = getVisibleWeeks();
  if (report.weeks.includes(state.sortKey) && !visibleWeeks.includes(state.sortKey)) {
    state.sortKey = "flow_order";
    state.sortDirection = "asc";
  }
  const records = getFilteredRecords();
  const reportData = state.view === "report" ? getReportRows(records) : null;
  const displayCount = reportData ? reportData.rows.length : records.length;
  const totalPages = Math.max(1, Math.ceil(displayCount / state.pageSize));
  if (state.page > totalPages) state.page = totalPages;
  document.getElementById("resultCount").textContent = `${formatNumber(displayCount)} records`;
  document.getElementById("pageInfo").textContent = `Page ${state.page} of ${totalPages}`;
  document.getElementById("prevPage").disabled = state.page <= 1;
  document.getElementById("nextPage").disabled = state.page >= totalPages;
  document.getElementById("tableTitle").textContent = state.view === "report" ? "Channel Report" : getViewConfig().title;
  Object.entries(viewButtons).forEach(([view, button]) => button.classList.toggle("active", view === state.view));
  buildTableHead();
  renderTable(records);
  renderFocusSummary(records);
  updateKpis(records);
}
Object.entries(filters).forEach(([key, control]) => {
  bindSingleSelect(control, key, (value) => applyFilterValue(key, value));
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".filter-select") && !event.target.closest(".ots-multiselect")) {
    closeSingleSelectMenus();
  }
});
Object.entries(channelReportControls).forEach(([key, control]) => {
  if (!control || key === "container" || key === "count" || key === "panel" || key === "toggle" || key === "reset" || key === "download" || key === "hide") return;
  control.addEventListener("change", () => {
    channelReportState[key] = control.value;
    renderChannelReports();
  });
});
if (channelReportControls.toggle) {
  channelReportControls.toggle.addEventListener("click", () => {
    channelReportState.open = !channelReportState.open;
    renderChannelReports();
  });
}
if (channelReportControls.hide) {
  channelReportControls.hide.addEventListener("click", () => {
    channelReportState.open = false;
    renderChannelReports();
  });
}
if (channelReportControls.reset) {
  channelReportControls.reset.addEventListener("click", resetChannelReports);
}
document.getElementById("resetButton").addEventListener("click", () => {
  state.filters = { market: "", city: "", mso_type: "", head_end: "", crn_no: "", channel_name: "", band: "", week_from: "", week_to: "", change: "" };
  state.sortKey = "flow_order";
  state.sortDirection = "asc";
  state.page = 1;
  render();
});
document.getElementById("prevPage").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; render(); } });
document.getElementById("nextPage").addEventListener("click", () => {
  const filteredRecords = getFilteredRecords();
  const totalRows = state.view === "report" ? getReportRows(filteredRecords).rows.length : filteredRecords.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / state.pageSize));
  if (state.page < totalPages) { state.page += 1; render(); }
});
Object.entries(viewButtons).forEach(([view, button]) => {
  button.addEventListener("click", () => {
    state.view = view;
    state.page = 1;
    render();
  });
});
if (table1DownloadButton) {
  table1DownloadButton.addEventListener("click", exportTable1Excel);
}
fullscreenButton.addEventListener("click", toggleFullscreen);
if (exitFullscreenButton) {
  exitFullscreenButton.addEventListener("click", async () => {
    if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === tableFullscreenScope) {
      const exited = await exitNativeFullscreen();
      if (!exited) {
        fullscreenState.usingNativeFullscreen = false;
        setFullscreen(false);
      }
      return;
    }
    setFullscreen(false);
  });
}
document.addEventListener("fullscreenchange", () => {
  const isTableFullscreen = document.fullscreenElement === tableFullscreenScope;
  fullscreenState.usingNativeFullscreen = isTableFullscreen;
  if (isTableFullscreen && !fullscreenState.active) {
    setFullscreen(true);
    return;
  }
  if (!isTableFullscreen && fullscreenState.active) {
    fullscreenState.usingNativeFullscreen = false;
    setFullscreen(false);
  }
});
window.addEventListener("resize", () => {
  const nextPageSize = getPageSize();
  if (nextPageSize !== state.pageSize) {
    state.pageSize = nextPageSize;
    state.page = 1;
    render();
  }
});
document.getElementById("downloadDashboardButton").addEventListener("click", downloadStandaloneDashboard);
syncFullscreenButtons();
render();
  </script>
  <script>
window.__NBHD_BENCHMARK_INITIAL_DATA__ = reportBundle.nbhd_benchmark;
  </script>
  <script>
__NBHD_BENCHMARK_SCRIPT__
  </script>
  <script>
window.__COMPARISON_INITIAL_DATA__ = reportBundle.comparison;
  </script>
  <script>
__COMPARISON_SCRIPT__
  </script>
  <script>
window.__NBHD_STANDALONE_DATA__ = reportBundle.nbhd;
  </script>
  <script>
__NBHD_SCRIPT__
  </script>
  <script>
window.__NBHD_WEEKWISE_INITIAL_DATA__ = reportBundle.nbhd_weekwise;
  </script>
  <script>
__NBHD_WEEKWISE_SCRIPT__
  </script>
  <script>
window.__OTS_STANDALONE_DATA__ = reportBundle.ots;
  </script>
  <script>
__OTS_SCRIPT__
  </script>
  <script>
window.__LANDING_STANDALONE_DATA__ = reportBundle.landing;
window.__LANDING_TRACKER_STANDALONE_DATA__ = reportBundle.landing;
  </script>
  <script>
__LANDING_SCRIPT__
  </script>
  <script>
__LANDING_TRACKER_SCRIPT__
  </script>
  <script>
__PLOTLY_GRAPH_SCRIPT__
  </script>
</body>
</html>
"""

    return (
        html.replace("__STYLE__", style_text + "\n" + plotly_style_text)
        .replace("__DEFAULT_CHANNEL_REPORTS__", default_channel_reports_js)
        .replace("__NBHD_BENCHMARK_SCRIPT__", nbhd_benchmark_script_text)
        .replace("__COMPARISON_SCRIPT__", comparison_script_text)
        .replace("__NBHD_SCRIPT__", nbhd_script_text)
        .replace("__NBHD_WEEKWISE_SCRIPT__", nbhd_weekwise_script_text)
        .replace("__OTS_SCRIPT__", ots_script_text)
        .replace("__LANDING_SCRIPT__", landing_script_text)
        .replace("__LANDING_TRACKER_SCRIPT__", landing_tracker_script_text)
        .replace("__PLOTLY_GRAPH_SCRIPT__", plotly_script_text)
        .replace("__EMBEDDED_BUNDLE_SCRIPT__", embedded_bundle_script)
    )


def build_api_payload(view: str, filters: dict[str, str], page: int, page_size: int, sort_key: str, sort_direction: str, force_refresh: bool = False) -> dict[str, Any]:
    report = load_report(force=force_refresh)
    weeks = report.get("weeks", [])
    records = report.get("records", [])
    filtered = filter_records(records, view, filters)
    sorted_records = sort_records(filtered, sort_key, sort_direction, view)
    page_records, total_count = paginate_records(sorted_records, page, page_size)
    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count else 1

    return {
        "generated_at": report.get("generated_at"),
        "view": view,
        "weeks": weeks,
        "filters": build_filters(records, view, filters, weeks),
        "summary": summarize_records(filtered, view, weeks),
        "focus_channels": summarize_focus_channels(filtered, view, weeks),
        "message": report.get("message", ""),
        "data_directory": str(DATA_DIR),
        "table": {
            "records": serialize_records(page_records, weeks),
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
        },
    }


def filter_nbhd_records(records: list[dict[str, Any]], filters: dict[str, str], search: str, ignore_key: str = "") -> list[dict[str, Any]]:
    search_text = normalize_text(search).lower()
    filtered: list[dict[str, Any]] = []
    for record in records:
        if filters["market"] and record["market"] != filters["market"] and ignore_key != "market":
            continue
        if filters["city"] and record["city"] != filters["city"] and ignore_key != "city":
            continue
        if filters["head_end"] and record["head_end"] != filters["head_end"] and ignore_key != "head_end":
            continue
        if filters.get("channel") and ignore_key != "channel":
            selected_channel = normalize_text(filters["channel"])
            channel_values = {normalize_text(value) for value in record.get("channels", {}).values()}
            if selected_channel not in channel_values:
                continue
        if search_text:
            haystack = " ".join(
                [
                    record["market"],
                    record["city"],
                    record["head_end"],
                    *[normalize_text(record["channels"].get(week)) for week in record["channels"]],
                    *[normalize_text(record["genres"].get(week)) for week in record["genres"]],
                    *[normalize_text(record["frequencies"].get(week)) for week in record["frequencies"]],
                ]
            ).lower()
            if search_text not in haystack:
                continue
        filtered.append(record)
    return filtered


def build_nbhd_filters(records: list[dict[str, Any]], current_filters: dict[str, str], search: str) -> dict[str, list[str]]:
    def values_for(field: str) -> list[str]:
        values = {
            normalize_text(record.get(field))
            for record in records
            if normalize_text(record.get(field))
        }
        return sorted(values, key=lambda value: value.lower())

    def channel_values() -> list[str]:
        values = {
            normalize_text(channel)
            for record in records
            for channel in record.get("channels", {}).values()
            if normalize_text(channel)
        }
        return sorted(values, key=lambda value: value.lower())

    return {
        "markets": values_for("market"),
        "cities": values_for("city"),
        "head_ends": values_for("head_end"),
        "channels": channel_values(),
    }


def serialize_nbhd_records(records: list[dict[str, Any]], weeks: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "market": record["market"],
            "city": record["city"],
            "head_end": record["head_end"],
            "channel_name": record.get("channel_name", ""),
            "position": record.get("position", 0),
            "is_reference": bool(record.get("is_reference")),
            "channels": {week: record["channels"].get(week, "") for week in weeks},
            "genres": {week: record["genres"].get(week, "") for week in weeks},
            "frequencies": {week: record["frequencies"].get(week) for week in weeks},
        }
        for record in records
    ]


def nbhd_default_visible_weeks(weeks: list[str], count: int = 2) -> list[str]:
    clean_weeks = [normalize_text(week) for week in weeks if normalize_text(week)]
    if not clean_weeks:
        return []
    return clean_weeks


def build_nbhd_api_payload(filters: dict[str, str], search: str, force_refresh: bool = False) -> dict[str, Any]:
    report = load_nbhd_report(force=force_refresh)
    weeks = report.get("weeks", [])
    records = report.get("records", [])
    filtered = filter_nbhd_records(records, filters, search)
    visible_weeks = nbhd_default_visible_weeks(weeks)
    return {
        "generated_at": report.get("generated_at"),
        "weeks": weeks,
        "visible_weeks": visible_weeks,
        "filters": build_nbhd_filters(records, filters, search),
        "search": search,
        "source_directory": report.get("source_directory", str(get_nbhd_source_dir())),
        "message": report.get("message", ""),
        "summary": {
            "total_headends": len(filtered),
        },
        "table": {
            "records": serialize_nbhd_records(filtered, weeks),
            "total_count": len(filtered),
        },
    }


def build_nbhd_export_bytes(filters: dict[str, str], search: str) -> bytes:
    payload = build_nbhd_api_payload(filters, search, force_refresh=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Neighbourhood Comparison"

    weeks = payload["weeks"]
    header_row_one = ["Market", "City", "Headend"]
    header_row_two = ["", "", ""]
    for group_name in ("Channel", "Genre", "Frequency"):
        header_row_one.extend([group_name] + [""] * (max(len(weeks) - 1, 0)))
        header_row_two.extend(weeks)

    sheet.append(header_row_one)
    sheet.append(header_row_two)

    if weeks:
        start_column = 4
        for _group_name in ("Channel", "Genre", "Frequency"):
            end_column = start_column + len(weeks) - 1
            sheet.merge_cells(start_row=1, start_column=start_column, end_row=1, end_column=end_column)
            start_column = end_column + 1
        sheet.merge_cells("A1:A2")
        sheet.merge_cells("B1:B2")
        sheet.merge_cells("C1:C2")

    for record in payload["table"]["records"]:
        row_values = [record["market"], record["city"], record["head_end"]]
        row_values.extend(record["channels"].get(week, "") for week in weeks)
        row_values.extend(record["genres"].get(week, "") for week in weeks)
        row_values.extend(record["frequencies"].get(week) for week in weeks)
        sheet.append(row_values)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def parse_multi_values(query: dict[str, list[str]], key: str) -> list[str]:
    # Support repeated query params and comma-separated values for multi-select filters.
    values: list[str] = []
    for raw in query.get(key, []):
        for part in raw.split(","):
            text = normalize_text(part)
            if text and text not in values:
                values.append(text)
    return values


def ots_visible_weeks(weeks: list[str], week_from: str, week_to: str) -> list[str]:
    # Slice dynamic week columns based on the selected from/to boundaries.
    if not weeks:
        return []
    if not week_from and not week_to:
        return weeks[max(0, len(weeks) - 8) :]
    start_index = weeks.index(week_from) if week_from in weeks else 0
    end_index = weeks.index(week_to) if week_to in weeks else len(weeks) - 1
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    return weeks[start_index : end_index + 1]


def ots_change_delta(record: dict[str, Any], weeks: list[str]) -> float | None:
    # Compare the latest visible week with the previous visible week.
    if len(weeks) < 2:
        return None
    previous = record["ots_values"].get(weeks[-2])
    current = record["ots_values"].get(weeks[-1])
    if previous is None or current is None:
        return None
    return round(float(current) - float(previous), 2)


def ots_change_type(record: dict[str, Any], weeks: list[str]) -> str:
    delta = ots_change_delta(record, weeks)
    if delta is None:
        return "no_change"
    if delta > 0:
        return "increase"
    if delta < 0:
        return "decrease"
    return "no_change"


def ots_matches_change_filter(change_type: str, filter_value: str) -> bool:
    if not filter_value:
        return True
    if filter_value == "changed":
        return change_type in {"increase", "decrease"}
    if filter_value == "no_change":
        return change_type == "no_change"
    return change_type == filter_value


def filter_ots_records(records: list[dict[str, Any]], filters: dict[str, Any], ignore_key: str = "") -> list[dict[str, Any]]:
    # Apply OTS market/channel/search/change filters against the current visible week range.
    visible_weeks = ots_visible_weeks(filters["all_weeks"], filters["week_from"], filters["week_to"])
    search_text = normalize_text(filters["search"]).lower()
    filtered: list[dict[str, Any]] = []
    for record in records:
        if filters["markets"] and record["market"] not in filters["markets"] and ignore_key != "markets":
            continue
        if filters["channels"] and record["channel"] not in filters["channels"] and ignore_key != "channels":
            continue
        if search_text:
            haystack = f"{record['market']} {record['channel']}".lower()
            if search_text not in haystack:
                continue
        if ignore_key != "change" and filters["change"]:
            change_type = ots_change_type(record, visible_weeks)
            if not ots_matches_change_filter(change_type, filters["change"]):
                continue
        filtered.append(record)
    return filtered


def build_ots_filters(records: list[dict[str, Any]], current_filters: dict[str, Any]) -> dict[str, list[str]]:
    # Build dynamic filter options scoped by the current selections.
    def values_for(field: str) -> list[str]:
        values = {
            normalize_text(record.get(field))
            for record in records
            if normalize_text(record.get(field))
        }
        return sorted(values, key=lambda value: value.lower())

    return {
        "markets": values_for("market"),
        "channels": values_for("channel"),
        "weeks": current_filters["all_weeks"],
        "change_options": ["", "changed", "no_change", "increase", "decrease"],
    }


def serialize_ots_records(records: list[dict[str, Any]], weeks: list[str]) -> list[dict[str, Any]]:
    # Keep only the visible week columns for the frontend payload.
    return [
        {
            "market": record["market"],
            "channel": record["channel"],
            "ots_values": {week: record["ots_values"].get(week) for week in weeks},
        }
        for record in records
    ]


def build_ots_api_payload(filters: dict[str, Any], force_refresh: bool = False) -> dict[str, Any]:
    # Produce one reusable payload for both the live dashboard and standalone HTML.
    report = load_ots_report(force=force_refresh)
    all_weeks = report.get("weeks", [])
    scoped_filters = {
        **filters,
        "all_weeks": all_weeks,
    }
    visible_weeks = ots_visible_weeks(all_weeks, filters["week_from"], filters["week_to"])
    filtered = filter_ots_records(report.get("records", []), scoped_filters)
    return {
        "generated_at": report.get("generated_at"),
        "weeks": all_weeks,
        "visible_weeks": visible_weeks,
        "filters": build_ots_filters(report.get("records", []), scoped_filters),
        "message": report.get("message", ""),
        "source_directory": report.get("source_directory", str(OTS_DATA_DIR)),
        "table": {
            "records": serialize_ots_records(filtered, visible_weeks),
            "total_count": len(filtered),
        },
    }


def build_ots_export_workbook(filters: dict[str, Any]) -> Workbook:
    # Create the OTS Excel export with dynamic week columns.
    payload = build_ots_api_payload(filters, force_refresh=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "OTS Comparison"
    header = ["Market", "Channel", *payload["visible_weeks"], "Change"]
    sheet.append(header)

    for record in payload["table"]["records"]:
        delta = ots_change_delta({"ots_values": record["ots_values"]}, payload["visible_weeks"])
        row = [record["market"], record["channel"]]
        row.extend(record["ots_values"].get(week) for week in payload["visible_weeks"])
        row.append(delta)
        sheet.append(row)
    return workbook


def build_ots_export_bytes(filters: dict[str, Any]) -> bytes:
    workbook = build_ots_export_workbook(filters)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_ots_csv_bytes(filters: dict[str, Any]) -> bytes:
    payload = build_ots_api_payload(filters, force_refresh=True)
    lines = [",".join(['"Market"', '"Channel"', *[f'"{week}"' for week in payload["visible_weeks"]], '"Change"'])]
    for record in payload["table"]["records"]:
        delta = ots_change_delta({"ots_values": record["ots_values"]}, payload["visible_weeks"])
        change_text = "" if delta is None else str(delta)
        cells = [record["market"], record["channel"], *[record["ots_values"].get(week) for week in payload["visible_weeks"]], change_text]
        safe_cells = ['"' + str("" if cell is None else cell).replace('"', '""') + '"' for cell in cells]
        lines.append(",".join(safe_cells))
    return "\n".join(lines).encode("utf-8")


def parse_int(value: str, default: int) -> int:
    try:
        return int(value or str(default))
    except (TypeError, ValueError):
        return default


def parse_api_request(query: dict[str, list[str]]) -> dict[str, Any]:
    view = (query.get("view", ["frequency"])[0] or "frequency").strip().lower()
    if view not in {"frequency", "rank", "band"}:
        view = "frequency"

    filters = {
        "market": (query.get("market", [""])[0] or "").strip(),
        "city": (query.get("city", [""])[0] or "").strip(),
        "mso_type": (query.get("mso_type", [""])[0] or "").strip(),
        "head_end": (query.get("head_end", [""])[0] or "").strip(),
        "crn_no": (query.get("crn_no", [""])[0] or "").strip(),
        "channel_name": (query.get("channel_name", [""])[0] or "").strip(),
        "band": (query.get("band", [""])[0] or "").strip(),
        "week": (query.get("week", [""])[0] or "").strip(),
        "change": (query.get("change", [""])[0] or "").strip(),
    }
    page = max(1, parse_int((query.get("page", ["1"])[0] or "1").strip(), 1))
    page_size = max(1, min(200, parse_int((query.get("page_size", ["30"])[0] or "30").strip(), 30)))
    sort_key = ((query.get("sort_key", ["flow_order"])[0] or "flow_order").strip() or "flow_order")
    sort_direction = (query.get("sort_direction", ["asc"])[0] or "asc").strip().lower()
    if sort_direction not in {"asc", "desc"}:
        sort_direction = "asc"
    force_refresh = (query.get("refresh", [""])[0] or "").strip() == "1"

    return build_api_payload(view, filters, page, page_size, sort_key, sort_direction, force_refresh)


def parse_nbhd_api_request(query: dict[str, list[str]]) -> dict[str, Any]:
    filters = {
        "market": (query.get("market", [""])[0] or "").strip(),
        "city": (query.get("city", [""])[0] or "").strip(),
        "head_end": (query.get("head_end", [""])[0] or "").strip(),
        "channel": (query.get("channel", [""])[0] or "").strip(),
    }
    search = (query.get("search", [""])[0] or "").strip()
    force_refresh = (query.get("refresh", [""])[0] or "").strip() == "1"
    return build_nbhd_api_payload(filters, search, force_refresh)


def parse_ots_api_request(query: dict[str, list[str]]) -> dict[str, Any]:
    filters = {
        "markets": parse_multi_values(query, "market"),
        "channels": parse_multi_values(query, "channel"),
        "week_from": (query.get("week_from", [""])[0] or "").strip(),
        "week_to": (query.get("week_to", [""])[0] or "").strip(),
        "change": (query.get("change", [""])[0] or "").strip(),
        "search": (query.get("search", [""])[0] or "").strip(),
    }
    force_refresh = (query.get("refresh", [""])[0] or "").strip() == "1"
    return build_ots_api_payload(filters, force_refresh)


def parse_ots_filters(query: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "markets": parse_multi_values(query, "market"),
        "channels": parse_multi_values(query, "channel"),
        "week_from": (query.get("week_from", [""])[0] or "").strip(),
        "week_to": (query.get("week_to", [""])[0] or "").strip(),
        "change": (query.get("change", [""])[0] or "").strip(),
        "search": (query.get("search", [""])[0] or "").strip(),
    }


def generate_standalone_dashboard() -> tuple[Path, Path]:
    ensure_directories()
    report = load_report(force=True)
    write_frequency_report_json(report)
    write_standalone_dashboard(report)
    return OUTPUT_JSON, OUTPUT_HTML


def generate_frequency_report_json() -> Path:
    ensure_directories()
    report = load_report(force=True)
    return write_frequency_report_json(report)


if __name__ == "__main__":
    json_path, html_path = generate_standalone_dashboard()
    print(f"Weekly data generated in: {DATA_DIR}")
    print(f"Report JSON updated: {json_path}")
    print(f"Standalone dashboard updated: {html_path}")
