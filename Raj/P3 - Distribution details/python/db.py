from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)

HEADEND_CSV_COLUMNS = [
    "Headend_ID",
    "Network_Name",
    "Headend",
    "State",
    "BARC_Market",
    "STB",
    "Landing_Channel",
    "Second_Landing_Channel",
    "Barker",
    "Second_Barker",
]

CHANNEL_CSV_COLUMNS = [
    "Headend_ID",
    "Week",
    "LCN",
    "Channel_Name",
    "Channel_Position",
]


def normalize_key_part(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().casefold()


def build_business_key(
    network_name: Any,
    headend: Any,
    state: Any,
    barc_market: Any,
) -> tuple[str, str, str, str]:
    return (
        normalize_key_part(network_name),
        normalize_key_part(headend),
        normalize_key_part(state),
        normalize_key_part(barc_market),
    )


def ensure_output_directories(root: Path) -> dict[str, Path]:
    processed_dir = root / "processed"
    dashboard_data_dir = root / "dashboard" / "data"
    comparison_dir = dashboard_data_dir / "comparison"
    processed_dir.mkdir(parents=True, exist_ok=True)
    dashboard_data_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    return {
        "processed_dir": processed_dir,
        "dashboard_data_dir": dashboard_data_dir,
        "comparison_dir": comparison_dir,
        "headend_csv": processed_dir / "headend_master.csv",
        "channel_csv": processed_dir / "channel_position.csv",
        "headends_json": dashboard_data_dir / "headends.json",
        "comparison_index_json": comparison_dir / "index.json",
        "filters_json": dashboard_data_dir / "filters.json",
    }


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False)


def fetch_existing_headends(headend_csv_path: Path) -> tuple[pd.DataFrame, dict[tuple[str, str, str, str], str]]:
    existing_df = read_csv_if_exists(headend_csv_path)
    if existing_df.empty:
        return pd.DataFrame(columns=HEADEND_CSV_COLUMNS), {}

    for column in HEADEND_CSV_COLUMNS:
        if column not in existing_df.columns:
            existing_df[column] = None

    existing_df = existing_df[HEADEND_CSV_COLUMNS].copy()
    existing_map: dict[tuple[str, str, str, str], str] = {}
    for record in existing_df.to_dict(orient="records"):
        existing_map[
            build_business_key(
                record["Network_Name"],
                record["Headend"],
                record["State"],
                record["BARC_Market"],
            )
        ] = str(record["Headend_ID"])

    return existing_df, existing_map


def next_headend_sequence(existing_df: pd.DataFrame) -> int:
    if existing_df.empty or "Headend_ID" not in existing_df.columns:
        return 1

    numeric_values = (
        existing_df["Headend_ID"]
        .dropna()
        .astype(str)
        .str.extract(r"^HED(\d+)$", expand=False)
        .dropna()
        .astype(int)
    )
    if numeric_values.empty:
        return 1
    return int(numeric_values.max()) + 1


def assign_headend_ids(
    existing_df: pd.DataFrame,
    existing_map: dict[tuple[str, str, str, str], str],
    headends_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[tuple[str, str, str, str], str], int]:
    next_sequence = next_headend_sequence(existing_df)
    new_count = 0

    records: list[dict[str, Any]] = []
    for record in headends_df.to_dict(orient="records"):
        key = build_business_key(
            record["Network_Name"],
            record["Headend"],
            record["State"],
            record["BARC_Market"],
        )
        headend_id = existing_map.get(key)
        if headend_id is None:
            headend_id = f"HED{next_sequence:06d}"
            existing_map[key] = headend_id
            next_sequence += 1
            new_count += 1

        record["Headend_ID"] = headend_id
        records.append(record)

    assigned_df = pd.DataFrame(records)
    if assigned_df.empty:
        assigned_df = pd.DataFrame(columns=HEADEND_CSV_COLUMNS)
    else:
        assigned_df = (
            assigned_df.drop_duplicates(subset=["Headend_ID"], keep="first")
            .reindex(columns=HEADEND_CSV_COLUMNS)
            .reset_index(drop=True)
        )

    return assigned_df, existing_map, new_count


def attach_headend_ids_to_channels(
    channels_df: pd.DataFrame,
    headend_map: dict[tuple[str, str, str, str], str],
) -> pd.DataFrame:
    if channels_df.empty:
        return pd.DataFrame(columns=CHANNEL_CSV_COLUMNS)

    resolved_records: list[dict[str, Any]] = []
    for record in channels_df.to_dict(orient="records"):
        key = build_business_key(
            record["Headend_Key_Network_Name"],
            record["Headend_Key_Headend"],
            record["Headend_Key_State"],
            record["Headend_Key_BARC_Market"],
        )
        headend_id = headend_map.get(key)
        if headend_id is None:
            raise KeyError(f"Unable to resolve Headend_ID for channel record key: {key}")

        resolved_records.append(
            {
                "Headend_ID": headend_id,
                "Week": normalize_date_value(record["Week"]),
                "LCN": normalize_scalar(record["LCN"]),
                "Channel_Name": normalize_scalar(record["Channel_Name"]),
                "Channel_Position": normalize_integer(record["Channel_Position"]),
            }
        )

    return pd.DataFrame(resolved_records).drop_duplicates(
        subset=CHANNEL_CSV_COLUMNS,
        keep="first",
    )


def merge_headends(existing_df: pd.DataFrame, assigned_df: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([existing_df, assigned_df], ignore_index=True)
    if combined.empty:
        return pd.DataFrame(columns=HEADEND_CSV_COLUMNS)

    for column in HEADEND_CSV_COLUMNS:
        if column not in combined.columns:
            combined[column] = None

    combined = (
        combined[HEADEND_CSV_COLUMNS]
        .drop_duplicates(subset=["Headend_ID"], keep="first")
        .sort_values("Headend_ID")
        .reset_index(drop=True)
    )
    return combined


def merge_channels(existing_df: pd.DataFrame, incoming_df: pd.DataFrame) -> pd.DataFrame:
    if existing_df.empty:
        existing_df = pd.DataFrame(columns=CHANNEL_CSV_COLUMNS)
    if incoming_df.empty:
        incoming_df = pd.DataFrame(columns=CHANNEL_CSV_COLUMNS)

    for column in CHANNEL_CSV_COLUMNS:
        if column not in existing_df.columns:
            existing_df[column] = None
        if column not in incoming_df.columns:
            incoming_df[column] = None

    existing_df = existing_df[CHANNEL_CSV_COLUMNS].copy()
    incoming_df = incoming_df[CHANNEL_CSV_COLUMNS].copy()
    existing_df["Week"] = existing_df["Week"].apply(normalize_date_value)
    incoming_df["Week"] = incoming_df["Week"].apply(normalize_date_value)

    combined = pd.concat([existing_df, incoming_df], ignore_index=True)
    combined = (
        combined.drop_duplicates(subset=CHANNEL_CSV_COLUMNS, keep="first")
        .sort_values(["Headend_ID", "Week", "Channel_Position", "LCN"], na_position="last")
        .reset_index(drop=True)
    )
    return combined


def build_headends_json(headends_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in headends_df.to_dict(orient="records"):
        rows.append(
            {
                "headend_id": normalize_scalar(record["Headend_ID"]),
                "network_name": normalize_scalar(record["Network_Name"]),
                "headend_location": normalize_scalar(record["Headend"]),
                "state": normalize_scalar(record["State"]),
                "barc_market": normalize_scalar(record["BARC_Market"]),
                "stbs": normalize_integer(record["STB"]),
                "landing_channel": normalize_scalar(record["Landing_Channel"]),
                "second_landing_channel": normalize_scalar(record["Second_Landing_Channel"]),
                "barker_channel": normalize_scalar(record["Barker"]),
                "second_barker_channel": normalize_scalar(record["Second_Barker"]),
            }
        )
    return rows


def build_filters_json(
    headends_df: pd.DataFrame,
    channels_df: pd.DataFrame,
    comparison_index: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    weeks = sorted(
        {
            normalize_date_value(value)
            for value in channels_df.get("Week", pd.Series(dtype=object)).tolist()
            if normalize_date_value(value)
        }
    )

    return {
        "states": sorted_unique(headends_df.get("State", pd.Series(dtype=object)).tolist()),
        "markets": sorted_unique(headends_df.get("BARC_Market", pd.Series(dtype=object)).tolist()),
        "locations": sorted_unique(headends_df.get("Headend", pd.Series(dtype=object)).tolist()),
        "weeks": weeks,
        "lcns": [],
        "channels": [],
        "comparison_pairs": comparison_index,
        "summary": {
            "last_updated": weeks[-1] if weeks else None,
            "total_headends": int(len(headends_df)),
            "total_channel_rows": int(len(channels_df)),
        },
    }


def build_comparison_chunks(
    channels_df: pd.DataFrame,
    comparison_dir: Path,
) -> tuple[list[dict[str, Any]], int]:
    if channels_df.empty:
        write_json(comparison_dir / "index.json", [])
        return [], 0

    normalized = channels_df.copy()
    normalized["Week"] = normalized["Week"].apply(normalize_date_value)
    normalized["LCN"] = normalized["LCN"].apply(normalize_scalar)
    normalized["Channel_Name"] = normalized["Channel_Name"].apply(normalize_scalar)
    normalized["Headend_ID"] = normalized["Headend_ID"].apply(normalize_scalar)
    normalized["Channel_Position"] = normalized["Channel_Position"].apply(normalize_integer)

    all_weeks = [week for week in sorted(normalized["Week"].dropna().unique().tolist()) if week]
    if len(all_weeks) < 2:
        write_json(comparison_dir / "index.json", [])
        return [], 0

    normalized = normalized.dropna(subset=["Headend_ID", "LCN", "Week"]).copy()
    if normalized.empty:
        write_json(comparison_dir / "index.json", [])
        return [], 0

    first_by_week = (
        normalized.sort_values(
            ["Headend_ID", "LCN", "Week", "Channel_Position"],
            na_position="last",
        )
        .drop_duplicates(subset=["Headend_ID", "LCN", "Week"], keep="first")
    )

    pivot = (
        first_by_week.pivot(
            index=["Headend_ID", "LCN"],
            columns="Week",
            values="Channel_Name",
        )
        .reindex(columns=all_weeks)
        .reset_index()
    )

    comparison_index: list[dict[str, Any]] = []
    total_rows = 0

    for week_from, week_to in zip(all_weeks[:-1], all_weeks[1:]):
        frame = pivot[["Headend_ID", "LCN", week_from, week_to]].copy()
        frame.columns = [
            "headend_id",
            "lcn",
            "week_from_channel",
            "week_to_channel",
        ]

        frame = frame[
            frame["week_from_channel"].notna() | frame["week_to_channel"].notna()
        ].copy()
        if frame.empty:
            continue

        frame["week_from"] = week_from
        frame["week_to"] = week_to
        frame["status"] = "Changed"
        frame.loc[
            frame["week_from_channel"].isna() & frame["week_to_channel"].notna(),
            "status",
        ] = "Added"
        frame.loc[
            frame["week_from_channel"].notna() & frame["week_to_channel"].isna(),
            "status",
        ] = "Removed"
        frame.loc[
            frame["week_from_channel"].eq(frame["week_to_channel"])
            & frame["week_from_channel"].notna(),
            "status",
        ] = "Same"

        chunk_df = frame[
            [
                "headend_id",
                "lcn",
                "week_from",
                "week_from_channel",
                "week_to",
                "week_to_channel",
                "status",
            ]
        ].copy()

        chunk_df["headend_id"] = chunk_df["headend_id"].apply(normalize_scalar)
        chunk_df["lcn"] = chunk_df["lcn"].apply(normalize_scalar)
        chunk_df["week_from_channel"] = chunk_df["week_from_channel"].apply(normalize_scalar)
        chunk_df["week_to_channel"] = chunk_df["week_to_channel"].apply(normalize_scalar)

        chunk_df = chunk_df.sort_values(
            by=["headend_id", "lcn"],
            key=lambda series: series.map(lcn_sort_key) if series.name == "lcn" else series,
            kind="stable",
        )
        chunk_records = chunk_df.to_dict(orient="records")
        chunk_name = f"{week_from}__{week_to}.json"
        chunk_path = comparison_dir / chunk_name
        write_json(chunk_path, chunk_records)

        comparison_index.append(
            {
                "week_from": week_from,
                "week_to": week_to,
                "file": f"./data/comparison/{chunk_name}",
                "record_count": int(len(chunk_records)),
            }
        )
        total_rows += int(len(chunk_records))

    write_json(comparison_dir / "index.json", comparison_index)
    return comparison_index, total_rows


def normalize_integer(value: Any) -> int | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return int(float(text))


def normalize_scalar(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_date_value(value: Any) -> str | None:
    if value is None or value == "" or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="raise")
        if pd.isna(parsed):
            return text
        return parsed.date().isoformat()
    except (ValueError, TypeError):
        return text


def sorted_unique(values: list[Any]) -> list[str]:
    cleaned = {
        str(value).strip()
        for value in values
        if value is not None and not pd.isna(value) and str(value).strip()
    }
    return sorted(cleaned, key=str.casefold)


def lcn_sort_key(value: Any) -> tuple[int, str]:
    text = str(value).strip()
    if text.isdigit():
        return (0, f"{int(text):010d}")
    return (1, text.casefold())


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_csv(path: Path, dataframe: pd.DataFrame) -> None:
    dataframe.to_csv(path, index=False, encoding="utf-8-sig")


def build_file_outputs(
    root: Path,
    headends_df: pd.DataFrame,
    channels_df: pd.DataFrame,
) -> dict[str, Any]:
    paths = ensure_output_directories(root)

    existing_headends_df, existing_headend_map = fetch_existing_headends(paths["headend_csv"])
    assigned_headends_df, headend_map, new_headend_id_count = assign_headend_ids(
        existing_df=existing_headends_df,
        existing_map=existing_headend_map,
        headends_df=headends_df,
    )

    incoming_channels_df = attach_headend_ids_to_channels(channels_df=channels_df, headend_map=headend_map)
    existing_channels_df = read_csv_if_exists(paths["channel_csv"])

    merged_headends_df = merge_headends(existing_headends_df, assigned_headends_df)
    merged_channels_df = merge_channels(existing_channels_df, incoming_channels_df)

    write_csv(paths["headend_csv"], merged_headends_df)
    write_csv(paths["channel_csv"], merged_channels_df)

    headends_json = build_headends_json(merged_headends_df)
    comparison_index, comparison_row_count = build_comparison_chunks(
        merged_channels_df,
        paths["comparison_dir"],
    )
    filters_json = build_filters_json(merged_headends_df, merged_channels_df, comparison_index)

    write_json(paths["headends_json"], headends_json)
    write_json(paths["filters_json"], filters_json)

    return {
        "new_headend_ids_assigned": new_headend_id_count,
        "headend_rows_in_batch": int(len(assigned_headends_df)),
        "channel_rows_in_batch": int(len(incoming_channels_df)),
        "headend_rows_total": int(len(merged_headends_df)),
        "channel_rows_total": int(len(merged_channels_df)),
        "comparison_rows_total": comparison_row_count,
        "processed_dir": str(paths["processed_dir"]),
        "dashboard_data_dir": str(paths["dashboard_data_dir"]),
    }


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    return value
