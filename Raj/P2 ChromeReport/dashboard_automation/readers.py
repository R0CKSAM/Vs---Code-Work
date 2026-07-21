from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import find_header_row, normalize_header, normalize_text


def _rename_columns(dataframe: pd.DataFrame, aliases: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for column in dataframe.columns:
        normalized_column = normalize_header(column)
        for canonical_name, accepted_aliases in aliases.items():
            if normalized_column in accepted_aliases:
                rename_map[column] = canonical_name
                break
    return dataframe.rename(columns=rename_map)


def _cleanup_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    cleaned = dataframe.copy()
    cleaned.columns = [normalize_text(column) for column in cleaned.columns]
    cleaned = cleaned.dropna(how="all")
    cleaned = cleaned.loc[:, [column for column in cleaned.columns if normalize_text(column)]]
    return cleaned.reset_index(drop=True)


def _coerce_numeric_columns(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")
    return dataframe


def read_distribution_details(file_path: Path, week_label: str) -> pd.DataFrame:
    aliases = {
        "Transmission": ("TRANSMISSION",),
        "Market": ("MARKET",),
        "Genre": ("GENRE",),
        "MSO Type": ("MSOTYPE",),
        "City": ("CITY",),
        "Head-End": ("HEADEND",),
        "Channel Name": ("CHANNELNAME", "CHANNEL"),
        "Frequency/LCN No": ("FREQUENCYLCNNO",),
        "Band": ("BAND",),
        "TV CH. No.": ("TVCHNO", "TVCHANNELNO"),
        "Audio": ("AUDIO",),
        "Video": ("VIDEO",),
        "Language": ("LANGUAGE",),
        "CRN No.": ("CRNNO",),
        "Rank Within Genre": ("RANKWITHINGENRE",),
    }
    header_row = find_header_row(file_path, "DistributionDetails", aliases)
    dataframe = pd.read_excel(
        file_path,
        sheet_name="DistributionDetails",
        header=header_row,
        engine="openpyxl",
    )
    dataframe = _cleanup_dataframe(_rename_columns(dataframe, aliases))
    drop_columns = [column for column in dataframe.columns if normalize_header(column).startswith("WEEK") and column != "Week"]
    if drop_columns:
        dataframe = dataframe.drop(columns=drop_columns)
    dataframe = _coerce_numeric_columns(dataframe, ["Frequency/LCN No", "TV CH. No.", "Rank Within Genre"])
    if "Week" in dataframe.columns:
        dataframe["Week"] = week_label
    else:
        dataframe.insert(0, "Week", week_label)
    return dataframe


def read_nbhd_details(file_path: Path, week_label: str) -> pd.DataFrame:
    aliases = {
        "Type": ("TYPE",),
        "Frequency": ("FREQUENCY", "FREQU"),
        "TV CH. No.": ("TVCHNO", "TVCHANNELNO"),
        "Market": ("MARKET",),
        "City": ("CITY",),
        "Head-End": ("HEADEND",),
        "Channel": ("CHANNEL",),
        "Genre": ("GENRE",),
    }
    header_row = find_header_row(file_path, "NBHD", aliases)
    dataframe = pd.read_excel(
        file_path,
        sheet_name="NBHD",
        header=header_row,
        engine="openpyxl",
    )
    dataframe = _cleanup_dataframe(_rename_columns(dataframe, aliases))
    dataframe = _coerce_numeric_columns(dataframe, ["Frequency", "TV CH. No."])
    if "Week" in dataframe.columns:
        dataframe["Week"] = week_label
    else:
        dataframe.insert(0, "Week", week_label)
    return dataframe


def read_ots_summary(file_path: Path, week_label: str) -> pd.DataFrame:
    aliases = {"Market": ("MARKET",)}
    header_row = find_header_row(file_path, "OTS Summary", aliases)
    dataframe = pd.read_excel(
        file_path,
        sheet_name="OTS Summary",
        header=header_row,
        engine="openpyxl",
    )
    dataframe = _cleanup_dataframe(dataframe)
    if dataframe.empty:
        return pd.DataFrame(columns=["Week", "Market", "Channel", "OTS"])

    market_column = next((column for column in dataframe.columns if normalize_header(column) == "MARKET"), dataframe.columns[0])
    dataframe = dataframe.rename(columns={market_column: "Market"})
    dataframe = dataframe.dropna(how="all", subset=["Market"])

    melted = dataframe.melt(id_vars=["Market"], var_name="Channel", value_name="OTS")
    melted["Market"] = melted["Market"].map(normalize_text)
    melted["Channel"] = melted["Channel"].map(normalize_text)
    melted["OTS"] = pd.to_numeric(melted["OTS"], errors="coerce")
    melted = melted.dropna(subset=["OTS"])
    melted = melted[(melted["Market"] != "") & (melted["Channel"] != "")]
    melted["OTS"] = melted["OTS"].map(lambda value: round(float(value) * 100, 2) if abs(float(value)) <= 1 else round(float(value), 2))
    melted.insert(0, "Week", week_label)
    return melted.reset_index(drop=True)
