from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "Data"
FRONTEND_DIR = ROOT / "frontend"
DIST_DIR = ROOT / "dist"
DIST_ASSETS_DIR = DIST_DIR / "assets"
MASTER_XLSX = DATA_DIR / "Master_Data.xlsx"
MASTER_PKL = DATA_DIR / "Master_Data.pkl"
BOOK1_XLSX = DATA_DIR / "Book1.xlsx"
PAYLOAD_PATH = DIST_ASSETS_DIR / "dashboard_payload.json"
CHART_JS_LOCAL = FRONTEND_DIR / "assets" / "vendor" / "chart.umd.js"
CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"


RENAME_MAP = {
    "Year&Week": "year_week",
    "Targets": "target",
    "Regions": "region",
    "Channel": "channel",
    "TimeBand": "time_band",
    "AMA 000's": "ama",
    "TSV 18hrs": "tsv",
    "Viewing Minutes'000": "viewing_minutes",
    "Cume Rch'000": "cume_reach",
}


def load_source_frame() -> pd.DataFrame:
    if MASTER_PKL.exists() and MASTER_XLSX.exists():
        if MASTER_PKL.stat().st_mtime >= MASTER_XLSX.stat().st_mtime:
            return pd.read_pickle(MASTER_PKL)
    if MASTER_XLSX.exists():
        return pd.read_excel(MASTER_XLSX, engine="openpyxl")
    if BOOK1_XLSX.exists():
        return pd.read_excel(BOOK1_XLSX, engine="openpyxl")
    raise FileNotFoundError("No source workbook found. Expected Master_Data.xlsx or Book1.xlsx in Data.")


def ensure_chart_js() -> None:
    CHART_JS_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    if CHART_JS_LOCAL.exists() and CHART_JS_LOCAL.stat().st_size > 100_000:
        return
    urllib.request.urlretrieve(CHART_JS_URL, CHART_JS_LOCAL)


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.rename(columns=RENAME_MAP).copy()
    required = list(RENAME_MAP.values())
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns in source data: {missing}")

    for text_column in ["year_week", "target", "region", "channel", "time_band"]:
        data[text_column] = data[text_column].astype(str).str.strip()

    for metric in ["ama", "tsv", "viewing_minutes", "cume_reach"]:
        data[metric] = pd.to_numeric(data[metric], errors="coerce").fillna(0.0)

    data["week_number"] = data["year_week"].str.extract(r"W\s*(\d+)", expand=False).astype(int)
    data["year_number"] = data["year_week"].str.extract(r"(\d{4})", expand=False).astype(int)
    data["week_sort"] = data["year_number"] * 100 + data["week_number"]
    return data


def build_payload(frame: pd.DataFrame) -> dict:
    ordered_weeks = (
        frame[["year_week", "week_sort"]]
        .drop_duplicates()
        .sort_values("week_sort")
        ["year_week"]
        .tolist()
    )
    metadata = {
        "row_count": int(len(frame)),
        "weeks": ordered_weeks,
        "targets": sorted(frame["target"].dropna().unique().tolist()),
        "regions": sorted(frame["region"].dropna().unique().tolist()),
        "channels": sorted(frame["channel"].dropna().unique().tolist()),
        "time_bands": sorted(frame["time_band"].dropna().unique().tolist()),
        "metrics": {
            "ama": "AMA (000s)",
            "tsv": "TSV",
            "viewing_minutes": "Viewing Minutes (000)",
            "cume_reach": "Cumulative Reach (000)",
        },
    }

    records = frame[
        [
            "year_week",
            "week_number",
            "week_sort",
            "target",
            "region",
            "channel",
            "time_band",
            "ama",
            "tsv",
            "viewing_minutes",
            "cume_reach",
        ]
    ].to_dict(orient="records")

    return {"metadata": metadata, "records": records}


def publish_frontend(payload: dict) -> None:
    DIST_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    PAYLOAD_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    index_template = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    embedded_payload = (
        "<script>window.__DASHBOARD_PAYLOAD__ = "
        f"{json.dumps(payload, separators=(',', ':'))};</script>"
    )
    (DIST_DIR / "index.html").write_text(
        index_template.replace("<!-- DASHBOARD_PAYLOAD -->", embedded_payload),
        encoding="utf-8",
    )

    for relative_path in [
        Path("styles.css"),
        Path("app.js"),
        Path("assets/vendor/chart.umd.js"),
    ]:
        source = FRONTEND_DIR / relative_path
        target = DIST_DIR / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> None:
    frame = load_source_frame()
    normalized = normalize(frame)
    payload = build_payload(normalized)
    ensure_chart_js()
    publish_frontend(payload)
    print(f"Dashboard built successfully: {DIST_DIR / 'index.html'}")
    print(f"Rows published: {payload['metadata']['row_count']:,}")


if __name__ == "__main__":
    main()
