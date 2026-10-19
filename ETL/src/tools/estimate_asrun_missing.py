"""Fill audience gaps transparently using measured history and rolling backtests."""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


AMAGI = "AMAGI 5-Minute Actual Concurrency"
YOUTUBE = "India TV YouTube Minute Concurrency"
SOURCES = ["FAST 5-Minute Concurrency", "STREAM 5-Minute Concurrency", AMAGI, YOUTUBE]
MODELS = ("weekday_median", "weekday_trend", "daytype_median")


class HistoricalEstimator:
    def __init__(self, series):
        self.series = series.sort_index()
        frame = series.rename("value").to_frame()
        frame["date"] = frame.index.normalize()
        frame["minute"] = frame.index.hour * 60 + frame.index.minute
        self.grid = frame.pivot(index="date", columns="minute", values="value").reindex(columns=range(1440))

    def predict(self, timestamp, model):
        day = timestamp.normalize()
        minute = timestamp.hour * 60 + timestamp.minute
        history = self.grid.loc[(self.grid.index < day) & (self.grid.index >= day - pd.Timedelta(days=56))]
        # One median per day prevents a densely sampled day dominating the estimate.
        daily = history.loc[:, max(0, minute-10):min(1439, minute+10)].median(axis=1).dropna()
        same_weekday = daily.loc[daily.index.dayofweek == day.dayofweek]
        same_daytype = daily.loc[(daily.index.dayofweek >= 5) == (day.dayofweek >= 5)]
        if model != "daytype_median" and len(same_weekday) >= 3:
            chosen, basis = same_weekday, "same weekday, +/-10 minutes"
        elif len(same_daytype) >= 4:
            chosen, basis = same_daytype, "same weekday/weekend type, +/-10 minutes"
        elif len(daily) >= 7:
            chosen, basis = daily, "all comparable days, +/-10 minutes"
        else:
            return None
        trend = 1.0
        if model == "weekday_trend":
            recent = daily.loc[daily.index >= day - pd.Timedelta(days=7)]
            previous = daily.loc[(daily.index >= day-pd.Timedelta(days=14)) & (daily.index < day-pd.Timedelta(days=7))]
            if len(recent) >= 3 and len(previous) >= 3 and previous.median() > 0:
                trend = float(np.clip(recent.median()/previous.median(), 0.5, 2.0))
        return dict(value=max(0, int(round(float(chosen.median())*trend))),
                    model=model, basis=basis, comparable_days=len(chosen),
                    history_from=str(chosen.index.min().date()), history_to=str(chosen.index.max().date()),
                    trend_factor=trend)

    def backtest(self, start, end, model):
        rows = []
        for day in pd.date_range(start, end):
            for minute in range(7*60, 24*60, 30):
                timestamp = day + pd.Timedelta(minutes=minute)
                actual = self.series.get(timestamp)
                if actual is None or pd.isna(actual):
                    continue
                forecast = self.predict(timestamp, model)
                if forecast is not None:
                    rows.append(dict(timestamp=str(timestamp), actual=float(actual), prediction=forecast["value"]))
        return pd.DataFrame(rows, columns=["timestamp", "actual", "prediction"])


def scores(frame):
    if frame.empty:
        return dict(samples=0, mae=None, wape_percent=None)
    absolute = (frame.actual-frame.prediction).abs()
    return dict(samples=len(frame), mae=float(absolute.mean()),
                wape_percent=float(100*absolute.sum()/frame.actual.abs().sum()) if frame.actual.abs().sum() else None)


def read_history(parsed, frame, end):
    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='1GB'")
    for column in ("AMAGI Channels", "AMAGI Platforms", "India TV YouTube Channel"):
        if frame[column].nunique() != 1:
            raise ValueError(f"Mixed filter scopes require separate models: {column}")
    channels = [x.strip() for x in frame["AMAGI Channels"].iloc[0].split("|")]
    platforms = [x.strip() for x in frame["AMAGI Platforms"].iloc[0].split("|")]
    yt_channels = [x.strip() for x in frame["India TV YouTube Channel"].iloc[0].split("|")]
    con.read_parquet(str(parsed / "amagi_minute.parquet")).create_view("amagi")
    amagi = con.execute(
        'SELECT minute_ist AS "timestamp",sum(concurrent_viewers) AS value FROM amagi '
        "WHERE list_contains(?,channel_name) AND list_contains(?,platform_name) "
        "AND minute_ist < ? GROUP BY 1 ORDER BY 1", [channels, platforms, end]).df()
    con.read_parquet(str(parsed / "youtube_video_minute.parquet")).create_view("videos")
    youtube = con.execute(
        'SELECT timestamp_ist AS "timestamp",sum(concurrent_viewers) AS value FROM videos '
        "WHERE list_contains(?,youtube_channel) AND timestamp_ist < ? GROUP BY 1 ORDER BY 1",
        [yt_channels, end]).df()
    con.read_parquet(str(parsed / "youtube_collector_minute.parquet")).create_view("collector")
    observed_zero = con.execute(
        'SELECT timestamp_ist AS "timestamp" FROM collector WHERE list_contains(?,youtube_channel) '
        "AND timestamp_ist < ? GROUP BY 1 HAVING "
        "count(*) FILTER (WHERE lower(collector_status) LIKE '%lookup_error%')=0 "
        "AND count(*) FILTER (WHERE trim(coalesce(collector_status,'')) <> '')>0",
        [yt_channels, end]).df()
    con.close()
    yt = youtube.set_index("timestamp").value
    zeros = pd.Series(0.0, index=pd.DatetimeIndex(observed_zero.timestamp))
    yt = yt.combine_first(zeros)
    amagi["bucket"] = amagi.timestamp.dt.floor("5min")
    grouped = amagi.groupby("bucket").agg(value=("value", "sum"), minutes=("timestamp", "nunique"))
    # Partial windows are missing, not zeros and not complete five-minute totals.
    ag = grouped.loc[grouped.minutes.eq(5), "value"]
    return {AMAGI: ag, YOUTUBE: yt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    original_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    original = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    result = original.copy()
    timestamps = pd.to_datetime(original["On-air IST"], format="%d-%m-%y %I:%M:%S %p")
    start = timestamps.min().normalize()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    histories = read_history(args.parsed, original, timestamps.max().normalize()+pd.Timedelta(days=1))
    labels = {AMAGI: "AMAGI", YOUTUBE: "YouTube"}
    estimated, recovered, methods = [dict() for _ in range(3)]
    details, model_audit = [], {}
    for column, series in histories.items():
        label = labels[column]
        estimator = HistoricalEstimator(series)
        selection = {model: scores(estimator.backtest(start-pd.Timedelta(days=14),
                                                     start-pd.Timedelta(days=8), model)) for model in MODELS}
        eligible = [model for model in MODELS if selection[model]["samples"] >= 30]
        if not eligible:
            raise RuntimeError(f"Insufficient historical backtest data for {label}")
        selected = min(eligible, key=lambda model: selection[model]["mae"])
        holdout = estimator.backtest(start-pd.Timedelta(days=7), start-pd.Timedelta(days=1), selected)
        if len(holdout) < 30:
            raise RuntimeError(f"Insufficient independent validation samples for {label}")
        error = float(np.quantile((holdout.actual-holdout.prediction).abs(), .9))
        model_audit[label] = dict(selected_model=selected, model_selection=selection,
                                  validation=scores(holdout), absolute_error_p90=error,
                                  selection_period=[str((start-pd.Timedelta(days=14)).date()),str((start-pd.Timedelta(days=8)).date())],
                                  validation_period=[str((start-pd.Timedelta(days=7)).date()),str((start-pd.Timedelta(days=1)).date())])
        holdout.to_csv(args.output_dir / f"{label.lower()}_backtest.csv", index=False)
        result[f"{label} Estimate Low"] = ""
        result[f"{label} Estimate High"] = ""
        cache = {}
        for index in original.index[original[column].str.strip().eq("")]:
            timestamp = timestamps.loc[index].floor("5min" if column == AMAGI else "min")
            measured = series.get(timestamp)
            if measured is not None and pd.notna(measured):
                result.loc[index, column] = str(int(round(float(measured))))
                recovered.setdefault(index, []).append(label)
                details.append(dict(row=index+2, source=label, timestamp=str(timestamp), status="Recovered measured",
                                    value=float(measured)))
                continue
            if timestamp not in cache:
                cache[timestamp] = estimator.predict(timestamp, selected)
            prediction = cache[timestamp]
            if prediction is None:
                continue
            result.loc[index, column] = str(prediction["value"])
            result.loc[index, f"{label} Estimate Low"] = str(max(0, int(np.floor(prediction["value"]-error))))
            result.loc[index, f"{label} Estimate High"] = str(int(np.ceil(prediction["value"]+error)))
            estimated.setdefault(index, []).append(label)
            methods.setdefault(index, []).append(f"{label}: {selected}")
            details.append(dict(row=index+2, source=label, timestamp=str(timestamp), status="Estimated", **prediction))
        print(label, json.dumps(model_audit[label]), flush=True)
    for index in original.index[original["Combined Concurrency"].str.strip().eq("")]:
        values = pd.to_numeric(result.loc[index, SOURCES], errors="coerce")
        if values.notna().all():
            result.loc[index, "Combined Concurrency"] = str(int(round(values.sum())))
    result["Data Quality"] = ["Contains statistical estimates" if i in estimated else
                              "Measured data recovered" if i in recovered else "Original data" for i in result.index]
    result["Estimated Fields"] = [" | ".join(estimated.get(i, [])) for i in result.index]
    result["Recovered Measured Fields"] = [" | ".join(recovered.get(i, [])) for i in result.index]
    result["Estimation Method"] = ["; ".join(methods.get(i, [])) for i in result.index]
    # No observed value, filter, event identifier or original coverage warning may change.
    for column in original.columns:
        populated = original[column].ne("")
        assert result.loc[populated,column].equals(original.loc[populated,column]), column
    assert len(result) == len(original)
    assert hashlib.sha256(args.input.read_bytes()).hexdigest() == original_hash
    output = args.output_dir / (args.input.stem + "_with_labelled_estimates.csv")
    result.to_csv(output, index=False, encoding="utf-8-sig")
    pd.DataFrame(details).to_csv(args.output_dir / "estimate_audit.csv", index=False, encoding="utf-8-sig")
    summary = dict(input=str(args.input), input_sha256=original_hash, output=str(output), rows=len(result),
                   estimated_cells=sum(map(len, estimated.values())), estimated_rows=len(estimated),
                   recovered_cells=sum(map(len, recovered.values())),
                   remaining_missing={c:int(result[c].eq("").sum()) for c in SOURCES+["Combined Concurrency"]},
                   models=model_audit)
    (args.output_dir / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    notes = ["ASRUN ESTIMATED AUDIENCE REPORT", "", "Original CSV is unchanged. Only empty audience and combined fields were filled.",
             "Estimated cells are NOT measured data. Do not describe them as verified delivery or billing figures.",
             "Data Quality and Estimated Fields identify affected rows. Original Coverage Status is retained.",
             "No video IDs, video titles or live-video counts were invented; original metadata is unchanged.",
             "Where audience is estimated, original zero active-video counts mean no captured video details, not verified zero live videos.",
             "AMAGI uses five-minute sums; YouTube uses the event's exact minute. Combined is the existing dashboard's mixed-basis sum, NOT unique viewers.",
             "Only the report's selected channels/platforms are used. Missing collection is never treated as zero.",
             "History uses up to 56 prior days, matching time within +/-10 minutes and weekday where sufficient history exists.",
             "Models are chosen on 28 Sep-4 Oct, then independently evaluated on 5-11 Oct; no target-date future data is used for forecasts.",
             "A recent/prior-week trend is used only if that model wins historical validation selection; growth is not forced.",
             "Low/High are estimate +/- the historical 90th percentile absolute error (lower bound >=0). These are empirical error bands, not guaranteed confidence intervals.",
             "Events, breaking news and outages may make actual audiences differ substantially from these estimates.", ""]
    for label, info in model_audit.items():
        metric = info["validation"]
        notes.append(f"{label}: {info['selected_model']}; validation samples={metric['samples']}; MAE={metric['mae']:.1f}; WAPE={metric['wape_percent']:.1f}%.")
    (args.output_dir / "METHOD-AND-LIMITATIONS.txt").write_text("\n".join(notes), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!='models'}, indent=2))


if __name__ == "__main__":
    main()
