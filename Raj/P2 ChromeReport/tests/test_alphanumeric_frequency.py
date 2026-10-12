from pathlib import Path

import pandas as pd

import app
from app import calculate_frequency_change, normalize_frequency
from dashboard_automation.readers import read_distribution_details


def test_normalize_frequency_preserves_alphanumeric_values() -> None:
    assert normalize_frequency("S12") == "S12"
    assert normalize_frequency("LCN-7") == "LCN-7"
    assert normalize_frequency("123A") == "123A"
    assert normalize_frequency("1020A") == "1020A"


def test_normalize_frequency_only_maps_unavailable_markers_to_none() -> None:
    assert normalize_frequency("Not Available") is None
    assert normalize_frequency("NA") is None
    assert normalize_frequency("N/A") is None
    assert normalize_frequency(711) == 711
    assert normalize_frequency("711.5") == 711.5


def test_alphanumeric_frequency_change_is_a_change() -> None:
    assert calculate_frequency_change("S12", "S13") == "change"
    assert calculate_frequency_change("S12", "S12") == "no_change"
    assert calculate_frequency_change(None, "S12") == "increase"
    assert calculate_frequency_change("S12", None) == "decrease"


def test_distribution_reader_does_not_coerce_alphanumeric_frequency(monkeypatch, tmp_path: Path) -> None:
    source = pd.DataFrame(
        {
            "Frequency/LCN No": [711, "S12", "Not Available"],
            "TV CH. No.": [711, 712, 713],
            "Rank Within Genre": [1, 2, 3],
        }
    )
    monkeypatch.setattr("dashboard_automation.readers.find_header_row", lambda *args, **kwargs: 0)
    monkeypatch.setattr("dashboard_automation.readers.pd.read_excel", lambda *args, **kwargs: source.copy())

    result = read_distribution_details(tmp_path / "week.xlsm", "Wk-38'26")

    assert result["Frequency/LCN No"].tolist() == [711, "S12", "Not Available"]


def test_report_joins_same_channel_when_mso_type_changes(monkeypatch, tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    distribution = history / "distribution_history.csv"
    pd.DataFrame(
        [
            {
                "Week": "Wk-37'26", "Transmission": "DIGITAL", "Market": "MARKET",
                "Genre": "NEWS", "MSO Type": "SITI", "City": "CITY", "Head-End": "HEADEND",
                "Channel Name": "INDIA TV", "Frequency/LCN No": "1020AF", "Band": "BST",
                "TV CH. No.": "", "Language": "HINDI", "CRN No.": "CHR001",
                "Rank Within Genre": 1,
            },
            {
                "Week": "Wk-38'26", "Transmission": "DIGITAL", "Market": "MARKET",
                "Genre": "NEWS", "MSO Type": "AXOM", "City": "CITY", "Head-End": "HEADEND",
                "Channel Name": "INDIA TV", "Frequency/LCN No": "1020AG", "Band": "BST",
                "TV CH. No.": "", "Language": "HINDI", "CRN No.": "CHR001",
                "Rank Within Genre": 1,
            },
        ]
    ).to_csv(distribution, index=False)
    nbhd = history / "nbhd_history.csv"
    ots = history / "ots_history.csv"
    nbhd.write_text("Week\nWk-37'26\n", encoding="utf-8")
    ots.write_text("Week\nWk-37'26\n", encoding="utf-8")

    monkeypatch.setattr(app, "HISTORY_DISTRIBUTION_CSV", distribution)
    monkeypatch.setattr(app, "LEGACY_HISTORY_DISTRIBUTION_CSV", tmp_path / "legacy-distribution.csv")
    monkeypatch.setattr(app, "HISTORY_NBHD_CSV", nbhd)
    monkeypatch.setattr(app, "LEGACY_HISTORY_NBHD_CSV", tmp_path / "legacy-nbhd.csv")
    monkeypatch.setattr(app, "HISTORY_OTS_CSV", ots)
    monkeypatch.setattr(app, "LEGACY_HISTORY_OTS_CSV", tmp_path / "legacy-ots.csv")

    report = app.build_report()

    assert len(report["records"]) == 1
    record = report["records"][0]
    assert record["frequencies"] == {"Wk-37'26": "1020AF", "Wk-38'26": "1020AG"}
    assert record["mso_type"] == "AXOM"
    assert record["changes"]["Wk-38'26"] == "change"
