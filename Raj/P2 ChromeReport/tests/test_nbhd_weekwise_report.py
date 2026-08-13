from pathlib import Path
import importlib.util


spec = importlib.util.spec_from_file_location("app", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def test_build_nbhd_weekwise_row_places_india_tv_in_c5_and_keeps_genres_paired():
    rows = [
        {"channel": "Channel 1", "genre": "Genre 1", "order_token": 101},
        {"channel": "Channel 2", "genre": "Genre 2", "order_token": 102},
        {"channel": "Channel 3", "genre": "Genre 3", "order_token": 103},
        {"channel": "Channel 4", "genre": "Genre 4", "order_token": 104},
        {"channel": "INDIA TV", "genre": "HINDI NEWS", "order_token": 105},
        {"channel": "Channel 6", "genre": "Genre 6", "order_token": 106},
        {"channel": "Channel 7", "genre": "Genre 7", "order_token": 107},
        {"channel": "Channel 8", "genre": "Genre 8", "order_token": 108},
        {"channel": "Channel 9", "genre": "Genre 9", "order_token": 109},
        {"channel": "Channel 10", "genre": "Genre 10", "order_token": 110},
    ]

    report_row = app.build_nbhd_weekwise_row("Wk-29'26", "Market", "City", "Headend", rows)

    assert report_row["c1"] == "Channel 1"
    assert report_row["c4"] == "Channel 4"
    assert report_row["c5"] == "INDIA TV"
    assert report_row["genre5"] == "HINDI NEWS"
    assert report_row["c9"] == "Channel 9"
    assert report_row["genre9"] == "Genre 9"
    assert "Channel 10" not in report_row.values()


def test_build_nbhd_weekwise_row_leaves_c5_blank_when_india_tv_missing():
    rows = [
        {"channel": "Channel 1", "genre": "Genre 1", "order_token": 101},
        {"channel": "Channel 2", "genre": "Genre 2", "order_token": 102},
        {"channel": "Channel 3", "genre": "Genre 3", "order_token": 103},
        {"channel": "Channel 4", "genre": "Genre 4", "order_token": 104},
        {"channel": "Channel 6", "genre": "Genre 6", "order_token": 106},
    ]

    report_row = app.build_nbhd_weekwise_row("Wk-29'26", "Market", "City", "Headend", rows)

    assert report_row["c1"] == "Channel 1"
    assert report_row["c4"] == "Channel 4"
    assert report_row["c5"] == ""
    assert report_row["genre5"] == ""
    assert report_row["c6"] == "Channel 6"
    assert report_row["genre6"] == "Genre 6"
