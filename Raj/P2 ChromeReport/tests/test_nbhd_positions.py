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


def test_build_nbhd_channel_rows_pads_to_fixed_groups_of_nine():
    rows = [
        {"channel": f"Channel {index}", "genre": "Genre", "frequency": 100 + index, "order_token": 100 + index}
        for index in range(1, 8)
    ]

    grouped = app.build_nbhd_channel_rows(rows)

    assert len(grouped) == 9
    assert [position for position, _row in grouped] == list(range(1, 10))
    assert grouped[7][1]["channel"] == "NA"
    assert grouped[8][1]["channel"] == "NA"
    assert grouped[8][1]["genre"] == "NA"
    assert grouped[8][1]["frequency"] == "NA"
    assert grouped[8][1]["group_index"] == 1
    assert grouped[8][1]["slot_index"] == 9


def test_build_nbhd_report_uses_fixed_slot_rows_with_na_padding(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    history_csv = history_dir / "nbhd_history.csv"
    history_csv.write_text(
        "\n".join(
            [
                "Week,Market,City,Head-End,Channel,Genre,Frequency,TV CH. No.",
                "Wk-30'26,Market,City,Headend,AAJ TAK,HINDI NEWS,701,101",
                "Wk-30'26,Market,City,Headend,INDIA TV,HINDI NEWS,702,102",
                "Wk-30'26,Market,City,Headend,ZEE NEWS,HINDI NEWS,703,103",
                "Wk-31'26,Market,City,Headend,INDIA TV,HINDI NEWS,801,101",
                "Wk-31'26,Market,City,Headend,AAJ TAK,HINDI NEWS,802,102",
                "Wk-31'26,Market,City,Headend,ZEE NEWS,HINDI NEWS,803,103",
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

    rows = [row for row in report["records"] if row["head_end"] == "Headend"]
    assert len(rows) == 9

    first_slot = next(row for row in rows if row["slot_index"] == 1)
    second_slot = next(row for row in rows if row["slot_index"] == 2)
    ninth_slot = next(row for row in rows if row["slot_index"] == 9)

    assert first_slot["channels"]["Wk-30'26"] == "AAJ TAK"
    assert first_slot["channels"]["Wk-31'26"] == "INDIA TV"
    assert first_slot["frequencies"]["Wk-31'26"] == 801
    assert second_slot["channels"]["Wk-30'26"] == "INDIA TV"
    assert second_slot["channels"]["Wk-31'26"] == "AAJ TAK"
    assert ninth_slot["channels"]["Wk-30'26"] == "NA"
    assert ninth_slot["channels"]["Wk-31'26"] == "NA"
    assert ninth_slot["genres"]["Wk-31'26"] == "NA"
    assert ninth_slot["frequencies"]["Wk-31'26"] == "NA"
