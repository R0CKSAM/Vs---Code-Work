from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook, load_workbook


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "frequency_report.json"

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
FIXED_COLUMNS = [
    "TRANSMISSION",
    "MARKET",
    "MSO TYPE",
    "CITY",
    "HEAD-END",
    "CHANNEL NAME",
    "BAND",
    "TV CH. No.",
    "CRN No.",
]
DISPLAY_COLUMNS = FIXED_COLUMNS + ["WEEK LABEL", "GENRE", "LANGUAGE", "NAME"]
FREQUENCY_COLUMN = "FREQUENCY/LCN NO"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_frequency(value: Any) -> float | int | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    return int(number) if number.is_integer() else number


def week_sort_key(label: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", label)
    return (int(match.group(1)), label) if match else (10**9, label)


def get_week_files() -> list[Path]:
    files = sorted(DATA_DIR.glob("Week*.xlsx"), key=lambda path: week_sort_key(path.stem))
    if not files:
        raise FileNotFoundError("No weekly Excel files found in the data folder.")
    return files


def prepare_week_rows(path: Path, fallback_label: str) -> tuple[str, list[dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    rows: list[dict[str, Any]] = []
    week_label = fallback_label

    for row_index, values in enumerate(sheet.iter_rows(min_row=1, max_col=16, values_only=True), start=1):
        if row_index == 1:
            continue

        row = {
            SOURCE_COLUMNS[index]: values[index] if index < len(values) else None
            for index in range(len(SOURCE_COLUMNS))
        }

        if row_index == 2 and normalize_text(row["WEEK LABEL"]):
            week_label = normalize_text(row["WEEK LABEL"])

        normalized = {column: normalize_text(row.get(column)) for column in DISPLAY_COLUMNS if column != "NAME"}
        normalized["NAME"] = normalize_text(row.get("CHANNEL NAME"))
        normalized[FREQUENCY_COLUMN] = normalize_frequency(row.get(FREQUENCY_COLUMN))
        normalized["ROW KEY"] = "||".join(normalized[column] for column in FIXED_COLUMNS)

        if not normalized["ROW KEY"].replace("|", ""):
            continue

        rows.append(normalized)

    workbook.close()

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped.setdefault(row["ROW KEY"], row)

    return week_label, list(deduped.values())


def calculate_pairwise_change(previous: float | int | None, current: float | int | None) -> str:
    if previous is None or current is None:
        return "missing"
    if current > previous:
        return "increase"
    if current < previous:
        return "decrease"
    return "no_change"


def summarize_records(records: list[dict[str, Any]], weeks: list[str]) -> dict[str, int]:
    increased = 0
    decreased = 0
    no_change = 0

    for record in records:
        for week in weeks[1:]:
            status = record["changes"][week]
            if status == "increase":
                increased += 1
            elif status == "decrease":
                decreased += 1
            elif status == "no_change":
                no_change += 1

    return {
        "total_channels": len(records),
        "increased": increased,
        "decreased": decreased,
        "no_change": no_change,
    }


def build_report() -> dict[str, Any]:
    weekly_data = [prepare_week_rows(path, path.stem) for path in get_week_files()]
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
                    "changes": {},
                },
            )
            record["frequencies"][week_label] = row[FREQUENCY_COLUMN]

    records = list(merged.values())

    for record in records:
        for week in weeks:
            record["frequencies"].setdefault(week, None)

        record["changes"][weeks[0]] = "baseline"
        for index in range(1, len(weeks)):
            previous = record["frequencies"][weeks[index - 1]]
            current = record["frequencies"][weeks[index]]
            record["changes"][weeks[index]] = calculate_pairwise_change(previous, current)

        unique_values = {record["frequencies"][week] for week in weeks}
        record["change_status"] = "NO" if len(unique_values) == 1 else "YES"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": weeks,
        "records": records,
        "summary": summarize_records(records, weeks),
        "filters": {
            "markets": sorted({record["market"] for record in records if record["market"]}),
            "mso_types": sorted({record["mso_type"] for record in records if record["mso_type"]}),
            "cities": sorted({record["city"] for record in records if record["city"]}),
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def report_is_stale() -> bool:
    if not OUTPUT_FILE.exists():
        return True
    output_time = OUTPUT_FILE.stat().st_mtime
    return any(path.stat().st_mtime > output_time for path in get_week_files())


def load_report() -> dict[str, Any]:
    if report_is_stale():
        return build_report()
    return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))


def apply_filters(records: list[dict[str, Any]], filters: dict[str, str], search: str) -> list[dict[str, Any]]:
    search_value = search.strip().lower()
    filtered = []

    for record in records:
        if filters.get("market") and record["market"] != filters["market"]:
            continue
        if filters.get("mso_type") and record["mso_type"] != filters["mso_type"]:
            continue
        if filters.get("city") and record["city"] != filters["city"]:
            continue
        if search_value:
            haystack = " ".join(
                [
                    record["channel_name"],
                    record["name"],
                    record["market"],
                    record["city"],
                    record["head_end"],
                ]
            ).lower()
            if search_value not in haystack:
                continue
        filtered.append(record)

    return filtered


def sort_records(records: list[dict[str, Any]], sort_key: str, sort_direction: str, weeks: list[str]) -> list[dict[str, Any]]:
    reverse = sort_direction == "desc"

    def value_for(record: dict[str, Any]) -> Any:
        if sort_key in weeks:
            value = record["frequencies"].get(sort_key)
        else:
            value = record.get(sort_key)
        if value is None or value == "":
            return (1, "")
        return (0, value)

    return sorted(records, key=value_for, reverse=reverse)


def paginate_records(records: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total_count = len(records)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    current_page = min(max(page, 1), total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return records[start:end], total_pages


def create_export_workbook(records: list[dict[str, Any]], weeks: list[str]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Chrome Report"

    headers = [
        "TRANSMISSION",
        "MARKET",
        "MSO TYPE",
        "CITY",
        "HEAD-END",
        "CHANNEL NAME",
        "BAND",
        "TV CH. No.",
        "CRN No.",
        "NAME",
    ]
    for week in weeks:
        headers.extend([week, f"{week} STATUS"])
    sheet.append(headers)

    for record in records:
        row = [
            record["transmission"],
            record["market"],
            record["mso_type"],
            record["city"],
            record["head_end"],
            record["channel_name"],
            record["band"],
            record["tv_ch_no"],
            record["crn_no"],
            record["name"],
        ]
        for week in weeks:
            row.extend([record["frequencies"][week], record["changes"][week]])
        sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    workbook.close()
    return buffer


app = Flask(__name__)


@app.route("/")
def index() -> str:
    load_report()
    return render_template("index.html")


@app.get("/api/frequency")
def api_frequency():
    report = load_report()
    weeks = report["weeks"]
    filters = {
        "market": request.args.get("market", ""),
        "mso_type": request.args.get("mso_type", ""),
        "city": request.args.get("city", ""),
    }
    search = request.args.get("search", "")
    sort_key = request.args.get("sort_key", "channel_name")
    sort_direction = request.args.get("sort_direction", "asc")
    page = max(1, request.args.get("page", default=1, type=int))
    page_size = min(100, max(10, request.args.get("page_size", default=25, type=int)))

    filtered = apply_filters(report["records"], filters, search)
    sorted_records = sort_records(filtered, sort_key, sort_direction, weeks)
    page_records, total_pages = paginate_records(sorted_records, page, page_size)

    return jsonify(
        {
            "generated_at": report["generated_at"],
            "weeks": weeks,
            "filters": report["filters"],
            "summary": summarize_records(filtered, weeks),
            "table": {
                "records": page_records,
                "page": min(page, total_pages),
                "page_size": page_size,
                "total_count": len(filtered),
                "total_pages": total_pages,
                "sort_key": sort_key,
                "sort_direction": sort_direction,
            },
        }
    )


@app.post("/api/export")
def export_frequency():
    payload = request.get_json(silent=True) or {}
    report = load_report()
    filters = {
        "market": payload.get("market", ""),
        "mso_type": payload.get("mso_type", ""),
        "city": payload.get("city", ""),
    }
    records = apply_filters(report["records"], filters, payload.get("search", ""))
    buffer = create_export_workbook(records, report["weeks"])

    return send_file(
        buffer,
        as_attachment=True,
        download_name="chrome_report_filtered.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    build_report()
    app.run(debug=True)
