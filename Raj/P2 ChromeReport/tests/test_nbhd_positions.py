from pathlib import Path
import importlib.util


spec = importlib.util.spec_from_file_location("app", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_enumerate_nbhd_positions_returns_all_sorted_rows():
    rows = [
        {"channel": "Channel 3", "order_token": 103},
        {"channel": "Channel 1", "order_token": 101},
        {"channel": "Channel 2", "order_token": 102},
    ]

    positioned = app.enumerate_nbhd_positions(rows)

    assert [position for position, _row in positioned] == [1, 2, 3]
    assert [row["channel"] for _position, row in positioned] == ["Channel 1", "Channel 2", "Channel 3"]


def test_build_nbhd_report_keeps_same_channel_on_one_row_when_position_changes(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    history_csv = history_dir / "nbhd_history.csv"
    history_csv.write_text(
        "\n".join(
            [
                "Week,Market,City,Head-End,Channel,Genre,Frequency,TV CH. No.",
                "Wk-30'26,Market,City,Headend,AAJ TAK,HINDI NEWS,,101",
                "Wk-30'26,Market,City,Headend,INDIA TV,HINDI NEWS,,102",
                "Wk-30'26,Market,City,Headend,ZEE NEWS,HINDI NEWS,,103",
                "Wk-31'26,Market,City,Headend,INDIA TV,HINDI NEWS,,101",
                "Wk-31'26,Market,City,Headend,AAJ TAK,HINDI NEWS,,102",
                "Wk-31'26,Market,City,Headend,ZEE NEWS,HINDI NEWS,,103",
            ]
        ),
        encoding="utf-8",
    )

    app.HISTORY_NBHD_CSV = history_csv
    app.LEGACY_HISTORY_NBHD_CSV = tmp_path / "legacy_nbhd_history.csv"
    app.HISTORY_DISTRIBUTION_CSV = history_dir / "distribution_history.csv"
    app.LEGACY_HISTORY_DISTRIBUTION_CSV = tmp_path / "legacy_distribution_history.csv"
    app.HISTORY_OTS_CSV = history_dir / "ots_history.csv"
    app.LEGACY_HISTORY_OTS_CSV = tmp_path / "legacy_ots_history.csv"
    app.HISTORY_DISTRIBUTION_CSV.write_text("x\n1\n", encoding="utf-8")
    app.HISTORY_OTS_CSV.write_text("x\n1\n", encoding="utf-8")
    app.NBHD_REPORT_CACHE["report"] = None
    app.NBHD_REPORT_CACHE["signature"] = None

    report = app.build_nbhd_report()

    india_rows = [row for row in report["records"] if row["head_end"] == "Headend" and row["channels"].get("Wk-30'26") == "INDIA TV"]
    assert len(india_rows) == 1
    assert india_rows[0]["channels"]["Wk-31'26"] == "INDIA TV"
