import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
from estimate_asrun_missing import HistoricalEstimator


def test_prediction_ignores_target_day_and_future():
    dates = pd.date_range("2026-08-01 12:00", "2026-10-19 12:00", freq="D")
    series = pd.Series(100.0, index=dates)
    target = pd.Timestamp("2026-10-12 12:00")
    before = HistoricalEstimator(series).predict(target, "weekday_trend")
    series.loc[series.index >= target.normalize()] = 100000000.0
    after = HistoricalEstimator(series).predict(target, "weekday_trend")
    assert before == after
    assert after["value"] == 100
    assert pd.Timestamp(after["history_to"]) < target.normalize()


def test_insufficient_history_is_not_filled_with_zero():
    series = pd.Series([0.0, 10.0], index=pd.to_datetime(["2026-10-10 12:00", "2026-10-11 12:00"]))
    assert HistoricalEstimator(series).predict(pd.Timestamp("2026-10-12 12:00"), "daytype_median") is None
