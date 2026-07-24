from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "generate_master_dashboard.py"
SPEC = importlib.util.spec_from_file_location("generate_master_dashboard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_master_cube_preserves_view_only_channels(tmp_path: Path) -> None:
    watch_dir = tmp_path / "watch_hours" / "daily_tables"
    latency_dir = tmp_path / "latency" / "profile"
    identity_dir = tmp_path / "identity"

    write_parquet(
        watch_dir / "daily_volume.parquet",
        [{"log_date": "2026-01-01", "source": "stream", "raw_ts_rows": 60, "approx_unique_ips": 4}],
    )
    write_parquet(
        watch_dir / "channel_audience_daily.parquet",
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "channel_name": "Channel A",
                "raw_ts_chunks": 60,
                "raw_watch_hours": 0.1,
                "approx_unique_ips": 4,
            }
        ],
    )
    write_parquet(
        latency_dir / "daily.parquet",
        [{"log_date": "2026-01-01", "source": "stream", "extension": "m3u8", "rows": 12}],
    )
    write_parquet(
        latency_dir / "channel_daily.parquet",
        [
            {"log_date": "2026-01-01", "source": "stream", "extension": "m3u8", "channel_name": "Channel A", "rows": 10},
            {"log_date": "2026-01-01", "source": "stream", "extension": "m3u8", "channel_name": "Channel B", "rows": 2},
        ],
    )
    write_parquet(
        identity_dir / "identity_daily.parquet",
        [{"log_date": "2026-01-01", "source": "stream", "total_devices": 3, "total_sessions": 5}],
    )
    write_parquet(
        identity_dir / "identity_channel_daily.parquet",
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "channel_name": "Channel A",
                "total_devices": 3,
                "total_sessions": 5,
            }
        ],
    )

    source_daily, channel_daily, ranges, _ = MODULE.build_master_frames(tmp_path)

    assert ranges == [{"source": "stream", "min_date": "2026-01-01", "max_date": "2026-01-01"}]
    assert set(channel_daily["channel_name"]) == {"Channel A", "Channel B"}
    view_only = channel_daily.loc[channel_daily["channel_name"].eq("Channel B")].iloc[0]
    assert view_only["total_views"] == 2
    assert view_only["watch_hours"] == 0
    assert view_only["clips_watched"] == 0
    assert channel_daily["total_views"].sum() == source_daily["total_views"].sum() == 12


def test_top_n_rows_returns_stable_descending_copy() -> None:
    frame = pd.DataFrame(
        [
            {"name": "A", "watch_hours": 10},
            {"name": "B", "watch_hours": 20},
            {"name": "C", "watch_hours": 20},
        ]
    )

    result = MODULE.top_n_rows(frame, 2, "watch_hours")

    assert result["name"].tolist() == ["B", "C"]
    assert frame["name"].tolist() == ["A", "B", "C"]


def test_compute_trend_compares_equal_recent_periods() -> None:
    frame = pd.DataFrame(
        {
            "log_date": pd.date_range("2026-01-01", periods=14).astype(str),
            "watch_hours": [10] * 7 + [12] * 7,
        }
    )

    trend = MODULE.compute_trend(frame, "watch_hours", days_back=7)

    assert trend["pct_change"] == 20.0
    assert trend["direction"] == "up"
    assert trend["delta"] == 14.0
    assert trend["period_days"] == 7
    assert trend["previous_start"] == "2026-01-01"
    assert trend["current_end"] == "2026-01-14"


def test_granular_device_model_labels_preserve_verified_detail() -> None:
    labels = MODULE.granular_device_model_labels(
        pd.Series(["Amazon", "Samsung", "", "Sony"]),
        pd.Series(["Fire TV Stick (Gen 3)", "SM-G998N", "", "Bravia 4K VH22"]),
        pd.Series(["AFTSSS", "", "", ""]),
        pd.Series(["", "", "Fire TV Cube", ""]),
        pd.Series(["3rd Gen", "", "2nd Gen", ""]),
    )

    assert labels.tolist() == [
        "Amazon Fire TV Stick (Gen 3)",
        "Samsung SM-G998N",
        "Fire TV Cube (2nd Gen)",
        "Sony Bravia 4K VH22",
    ]


def test_build_data_adds_summary_and_section_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_daily = pd.DataFrame(
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "watch_hours": 10.0,
                "clips_watched": 6_000,
                "ip_users": 100,
                "total_views": 50,
                "total_devices": 80,
                "total_sessions": 120,
            },
            {
                "log_date": "2026-01-02",
                "source": "stream",
                "watch_hours": 15.0,
                "clips_watched": 9_000,
                "ip_users": 150,
                "total_views": 75,
                "total_devices": 110,
                "total_sessions": 170,
            },
        ]
    )
    channel_daily = source_daily.assign(channel_name=["Channel A", "Channel B"])
    ranges = [{"source": "stream", "min_date": "2026-01-01", "max_date": "2026-01-02"}]
    ua_daily = pd.DataFrame(
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "channel_name": None,
                "dimension": "device",
                "label": "Smart TV",
                "raw_ts_rows": 100,
            }
        ]
    )
    market_daily = pd.DataFrame(
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "scope": "source",
                "channel_name": None,
                "market_level": "india_state",
                "label": "Delhi",
                "raw_ts_rows": 100,
                "watch_hours": 1.0,
            }
        ]
    )
    geo_source_daily = pd.DataFrame(
        [
            {
                "log_date": "2026-01-01",
                "source": "stream",
                "country": "IN",
                "state": "Delhi",
                "city": "NEWDELHI",
                "raw_ts_rows": 100,
                "approx_unique_ips": 10,
            }
        ]
    )
    geo_channel_daily = geo_source_daily.assign(channel_name="Channel A")

    monkeypatch.setattr(
        MODULE,
        "build_master_frames",
        lambda _root: (source_daily, channel_daily, ranges, {"watch_source": "watch.parquet"}),
    )
    monkeypatch.setattr(
        MODULE,
        "build_ua_daily",
        lambda _root, _ranges: (ua_daily, {"ua_source": "ua.parquet"}),
    )
    monkeypatch.setattr(
        MODULE,
        "build_market_daily",
        lambda _root, _ranges: (market_daily, {"market_source": "market.parquet"}),
    )
    monkeypatch.setattr(
        MODULE,
        "build_raw_geo_hierarchy_daily",
        lambda _root, _ranges: (
            geo_source_daily,
            geo_channel_daily,
            {"geo_hierarchy_source": "geo.parquet"},
        ),
    )

    data, _, _ = MODULE.build_data(tmp_path, "Test Dashboard")

    assert data["summary"]["total_watch_hours"] == 25.0
    assert data["summary"]["total_clips_watched"] == 15_000
    assert data["summary"]["total_ip_users"] == 250
    assert data["summary"]["total_views"] == 125
    assert data["sections"]["overview"]["top_channels"][0]["channel_name"] == "Channel B"
    assert len(data["sections"]["by_channel"]["channel_daily_records"]) == 2
    assert data["sections"]["devices"]["ua_daily"] == data["ua_daily"]
    assert data["sections"]["geography"]["geo_source_daily"] == data["geo_source_daily"]
    assert set(data["input_files"]) == {
        "watch_source",
        "ua_source",
        "market_source",
        "geo_hierarchy_source",
    }
