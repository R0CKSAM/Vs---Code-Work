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
