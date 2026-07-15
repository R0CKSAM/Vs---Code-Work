import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MERGED_JSON_PATH = DATA_DIR / "merged_data.json"
KPI_JSON_PATH = DATA_DIR / "kpi_summary.json"
MERGED_JS_PATH = DATA_DIR / "merged_data.js"
KPI_JS_PATH = DATA_DIR / "kpi_summary.js"
DEFAULT_VIEW_JS_PATH = DATA_DIR / "default_view.js"
CHART_JSON_PATH = DATA_DIR / "chart_data.json"
CHART_JS_PATH = DATA_DIR / "chart_data.js"

SOURCE_COLUMNS = {
    "TRANSMISSION": "transmission",
    "MARKET": "market",
    "MSO TYPE": "mso_type",
    "CITY": "city",
    "HEAD-END": "head_end",
    "CHANNEL NAME": "channel_name",
    "BAND": "band",
    "TV CH. No.": "tv_channel_no",
    "CRN No.": "cr_no",
    "FREQUENCY/LCN NO": "frequency",
}

MERGE_KEYS = [
    "transmission",
    "mso",
    "market",
    "mso_type",
    "city",
    "head_end",
    "channel_name",
    "band",
    "tv_channel_no",
    "cr_no",
]

FREQUENCY_COLUMNS = ["w1_frequency", "w2_frequency", "w3_frequency", "w4_frequency"]


def clean_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_channel_name(value):
    text = clean_value(value)
    if not text:
        return ""
    normalized_parts = []
    for part in text.split():
        token = part.strip()
        if not token:
            continue
        if token.isupper() and len(token) <= 3:
            normalized_parts.append(token)
        else:
            normalized_parts.append(token.capitalize())
    return " ".join(normalized_parts)


def numeric_or_blank(value):
    text = clean_value(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def extract_week_label(path, header_first_cell):
    header_text = clean_value(header_first_cell)
    if header_text and header_text.lower().startswith("week") and header_text.lower() != "week":
        return header_text
    stem = path.stem
    if stem.lower().startswith("week"):
        suffix = stem[4:]
        return f"Week {suffix}" if suffix else stem
    return stem


def load_week_dataframe(path):
    required_columns = list(SOURCE_COLUMNS.keys())
    frame = pd.read_excel(
        path,
        engine="openpyxl",
        usecols=required_columns,
        dtype=object,
    )

    if frame.empty:
        return frame, extract_week_label(path, "")

    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")

    week_label = extract_week_label(path, "")
    frame = frame.rename(columns=SOURCE_COLUMNS)
    for column in frame.columns:
        frame[column] = frame[column].map(clean_value)

    frame = frame[frame.apply(lambda row: any(row.values), axis=1)].copy()
    frame["channel_name"] = frame["channel_name"].map(normalize_channel_name)
    frame["mso"] = frame["head_end"]
    frame["week"] = week_label
    frame["frequency"] = frame["frequency"].map(numeric_or_blank)

    dedup_columns = MERGE_KEYS + ["week"]
    frame = frame.drop_duplicates(subset=dedup_columns, keep="last")
    return frame, week_label


def calculate_change_status(row):
    values = [row[column] for column in FREQUENCY_COLUMNS]
    if all(value == values[0] for value in values):
        return "NO CHANGE"
    return "CHANGED"


def flatten_frequency(value):
    if pd.isna(value):
        return None
    return numeric_or_blank(value)


def build_records():
    excel_files = sorted(DATA_DIR.glob("*.xlsx"))
    if len(excel_files) < 4:
        raise FileNotFoundError("Expected four weekly Excel files inside the data folder.")

    selected_files = excel_files[:4]
    weekly_frames = []
    week_labels = []

    for index, path in enumerate(selected_files, start=1):
        frame, week_label = load_week_dataframe(path)
        if frame.empty:
            continue
        week_labels.append(week_label)
        frame = frame[MERGE_KEYS + ["frequency"]].rename(columns={"frequency": f"w{index}_frequency"})
        weekly_frames.append(frame)

    if not weekly_frames:
        raise ValueError("No rows were loaded from the provided Excel files.")

    merged = weekly_frames[0]
    for frame in weekly_frames[1:]:
        merged = merged.merge(frame, on=MERGE_KEYS, how="outer")

    for column in FREQUENCY_COLUMNS:
        if column not in merged.columns:
            merged[column] = None

    merged["week"] = " | ".join(week_labels)
    merged["change_status"] = merged.apply(calculate_change_status, axis=1)

    ordered_columns = [
        "week",
        "transmission",
        "mso",
        "market",
        "mso_type",
        "city",
        "head_end",
        "channel_name",
        "band",
        "tv_channel_no",
        "cr_no",
        *FREQUENCY_COLUMNS,
        "change_status",
    ]
    merged = merged[ordered_columns].sort_values(
        by=["channel_name", "market", "city", "head_end"],
        kind="stable",
        na_position="last",
    )

    for column in FREQUENCY_COLUMNS:
        merged[column] = merged[column].apply(flatten_frequency)

    records = merged.to_dict(orient="records")
    return records, selected_files


def build_kpi_summary(records, source_files):
    frame = pd.DataFrame(records)

    india_tv_rows = frame[frame["channel_name"] == "India TV"] if not frame.empty else pd.DataFrame()
    india_tv_values = []
    if not india_tv_rows.empty:
        for column in FREQUENCY_COLUMNS:
            india_tv_values.extend(
                [
                    value
                    for value in india_tv_rows[column].tolist()
                    if isinstance(value, (int, float))
                ]
            )

    highest_channel = None
    highest_frequency = None
    for record in records:
        for column in FREQUENCY_COLUMNS:
            value = record.get(column)
            if isinstance(value, (int, float)) and (highest_frequency is None or value > highest_frequency):
                highest_frequency = value
                highest_channel = record.get("channel_name")

    return {
        "source_files": [path.name for path in source_files],
        "record_count": int(len(records)),
        "total_markets": int(frame["market"].nunique()) if not frame.empty else 0,
        "total_msos": int(frame["mso"].nunique()) if not frame.empty else 0,
        "total_channels": int(frame["channel_name"].nunique()) if not frame.empty else 0,
        "changed_records": int((frame["change_status"] == "CHANGED").sum()) if not frame.empty else 0,
        "no_change_records": int((frame["change_status"] == "NO CHANGE").sum()) if not frame.empty else 0,
        "india_tv_average_frequency": round(sum(india_tv_values) / len(india_tv_values), 2) if india_tv_values else 0,
        "highest_frequency_channel": highest_channel or "",
        "highest_frequency_value": highest_frequency if highest_frequency is not None else 0,
    }


def build_chart_data(records):
    frame = pd.DataFrame(records)
    if frame.empty:
        return {
            "weekly_trend": {"labels": ["W1", "W2", "W3", "W4"], "values": [0, 0, 0, 0]},
            "top_markets": {"labels": [], "values": []},
            "top_msos": {"labels": [], "values": []},
            "frequency_distribution": {"labels": [], "values": []},
        }

    weekly_values = []
    for column in FREQUENCY_COLUMNS:
        numeric_series = pd.to_numeric(frame[column], errors="coerce").dropna()
        weekly_values.append(round(float(numeric_series.mean()), 2) if not numeric_series.empty else 0)

    changed_frame = frame[frame["change_status"] == "CHANGED"]
    top_markets = changed_frame["market"].value_counts().head(8)
    top_msos = changed_frame["mso"].value_counts().head(8)

    distribution_source = pd.to_numeric(
        pd.concat([frame[column] for column in FREQUENCY_COLUMNS], ignore_index=True),
        errors="coerce",
    ).dropna()
    if distribution_source.empty:
        distribution_labels = []
        distribution_values = []
    else:
        bins = [0, 100, 300, 600, 1000, 3000, 10000, float("inf")]
        labels = ["0-99", "100-299", "300-599", "600-999", "1000-2999", "3000-9999", "10000+"]
        bucketed = pd.cut(distribution_source, bins=bins, labels=labels, right=False)
        distribution = bucketed.value_counts().sort_index()
        distribution_labels = distribution.index.astype(str).tolist()
        distribution_values = distribution.tolist()

    return {
        "weekly_trend": {"labels": ["W1", "W2", "W3", "W4"], "values": weekly_values},
        "top_markets": {"labels": top_markets.index.tolist(), "values": top_markets.tolist()},
        "top_msos": {"labels": top_msos.index.tolist(), "values": top_msos.tolist()},
        "frequency_distribution": {"labels": distribution_labels, "values": distribution_values},
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def write_js_variable(path, variable_name, payload):
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    path.write_text(f"window.{variable_name}={serialized};\n", encoding="utf-8")


def main():
    records, source_files = build_records()
    default_records = [record for record in records if record["channel_name"] == "India TV"]
    merged_payload = {
        "meta": {
            "source_files": [path.name for path in source_files],
            "default_channel": "India TV",
        },
        "records": records,
    }
    default_payload = {
        "meta": {
            "source_files": [path.name for path in source_files],
            "default_channel": "India TV",
            "mode": "default_view",
        },
        "records": default_records,
    }
    kpi_summary = build_kpi_summary(records, source_files)
    chart_data = build_chart_data(records)

    write_json(MERGED_JSON_PATH, merged_payload)
    write_json(KPI_JSON_PATH, kpi_summary)
    write_json(CHART_JSON_PATH, chart_data)
    write_js_variable(MERGED_JS_PATH, "CHROME_REPORT_MERGED_DATA", merged_payload)
    write_js_variable(KPI_JS_PATH, "CHROME_REPORT_KPI_SUMMARY", kpi_summary)
    write_js_variable(DEFAULT_VIEW_JS_PATH, "CHROME_REPORT_DEFAULT_VIEW", default_payload)
    write_js_variable(CHART_JS_PATH, "CHROME_REPORT_CHART_DATA", chart_data)

    print(f"Wrote {MERGED_JSON_PATH}")
    print(f"Wrote {KPI_JSON_PATH}")
    print(f"Wrote {CHART_JSON_PATH}")
    print(f"Wrote {MERGED_JS_PATH}")
    print(f"Wrote {KPI_JS_PATH}")
    print(f"Wrote {DEFAULT_VIEW_JS_PATH}")
    print(f"Wrote {CHART_JS_PATH}")
    print(f"Records: {len(records)}")


if __name__ == "__main__":
    main()
