from app import ots_change_delta, ots_change_type


def test_ots_change_delta_returns_increase_when_previous_is_missing() -> None:
    record = {"ots_values": {"Wk-32'26": None, "Wk-33'26": 4.5}}

    assert ots_change_delta(record, ["Wk-32'26", "Wk-33'26"]) == 4.5
    assert ots_change_type(record, ["Wk-32'26", "Wk-33'26"]) == "increase"


def test_ots_change_delta_returns_decrease_when_current_is_missing() -> None:
    record = {"ots_values": {"Wk-32'26": 3.25, "Wk-33'26": None}}

    assert ots_change_delta(record, ["Wk-32'26", "Wk-33'26"]) == -3.25
    assert ots_change_type(record, ["Wk-32'26", "Wk-33'26"]) == "decrease"


def test_ots_change_type_is_missing_when_both_weeks_are_missing() -> None:
    record = {"ots_values": {"Wk-32'26": None, "Wk-33'26": None}}

    assert ots_change_delta(record, ["Wk-32'26", "Wk-33'26"]) is None
    assert ots_change_type(record, ["Wk-32'26", "Wk-33'26"]) == "missing"
