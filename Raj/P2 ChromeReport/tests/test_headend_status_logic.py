from pathlib import Path

from openpyxl import Workbook

import app
from headend_status import classify_remark, load_headend_status_data


def write_status_workbook(path: Path, remarks: str, crn_no: str = "CHR001") -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Networks Details"
    sheet.append([None, "LL", None, None, "Wk-39, 2026"])
    sheet.append([])
    sheet.append([])
    sheet.append([])
    sheet.append([None, "TRANSMISSION", "STATE", "MARKET", "CITY", "NETWORK", "CRN NO", "REMARKS"])
    sheet.append([None, "DIGITAL", "STATE", "MARKET", "CITY", "HEADEND", crn_no, remarks])
    workbook.save(path)


def frequency_record(crn_no: str = "CHR001") -> dict:
    return {
        "transmission": "DIGITAL",
        "market": "MARKET",
        "city": "CITY",
        "head_end": "HEADEND",
        "crn_no": crn_no,
        "channel_name": "INDIA TV",
        "frequencies": {"Wk-38'26": 123, "Wk-39'26": None},
    }


def test_status_workbook_parser_reads_week_and_addition(tmp_path: Path) -> None:
    write_status_workbook(tmp_path / "Add-Closed Networks Details Wk-39' 2026.xlsx", "ADDITION")
    data = load_headend_status_data(tmp_path)

    assert data.available_weeks == {"Wk-39'26"}
    assert len(data.events) == 1
    assert data.events[0].status == "available"
    assert data.events[0].network == "HEADEND"


def test_closed_headend_suppresses_channel_closure(tmp_path: Path) -> None:
    write_status_workbook(tmp_path / "Add-Closed Networks Details Wk-39' 2026.xlsx", "CLOSURE")
    data = load_headend_status_data(tmp_path)
    record = frequency_record()

    app.apply_headend_status_logic([record], ["Wk-38'26", "Wk-39'26"], data)

    assert record["closure_outcomes"]["Wk-39'26"] == "headend_closed"
    assert record["headend_statuses"]["Wk-39'26"]["status"] == "closed"


def test_missing_closure_means_tracked_channel_closed_at_available_headend(tmp_path: Path) -> None:
    write_status_workbook(tmp_path / "Add-Closed Networks Details Wk-39' 2026.xlsx", "ADDITION", "OTHER-CRN")
    data = load_headend_status_data(tmp_path)
    record = frequency_record()

    app.apply_headend_status_logic([record], ["Wk-38'26", "Wk-39'26"], data)

    assert record["closure_outcomes"]["Wk-39'26"] == "channel_closed"
    assert record["headend_statuses"]["Wk-39'26"]["status"] == "available"


def test_remark_classification_supports_common_closure_words() -> None:
    assert classify_remark("Head-end closed") == "closed"
    assert classify_remark("Deletion") == "closed"
    assert classify_remark("Addition") == "available"
