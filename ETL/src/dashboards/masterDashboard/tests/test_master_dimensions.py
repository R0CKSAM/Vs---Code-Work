from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "generate_master_dashboard.py"
SPEC = importlib.util.spec_from_file_location("generate_master_dashboard_dimensions", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_compact_payload_round_trip_preserves_null_scope() -> None:
    frame = pd.DataFrame(
        [
            {
                "log_date": "2026-07-14",
                "source": "stream",
                "channel_name": None,
                "dimension": "device",
                "label": "Smart TV",
                "raw_ts_rows": 60,
            },
            {
                "log_date": "2026-07-14",
                "source": "fast",
                "channel_name": "India TV",
                "dimension": "os",
                "label": "Tizen",
                "raw_ts_rows": 120,
            },
        ]
    )

    payload = MODULE.compact_payload(
        frame,
        ["log_date", "source", "channel_name", "dimension", "label"],
        ["raw_ts_rows"],
    )
    restored = MODULE.expand_compact_payload(payload)

    assert restored.loc[0, "channel_name"] is None
    assert restored.loc[1, "channel_name"] == "India TV"
    assert restored["raw_ts_rows"].tolist() == [60, 120]


def test_market_rows_normalizes_states_and_excludes_india_from_countries() -> None:
    frame = pd.DataFrame(
        [
            {"log_date": "2026-07-14", "source": "stream", "country": "IN", "state": "Chattisgarh", "raw_ts_rows": 60},
            {"log_date": "2026-07-14", "source": "stream", "country": "IN", "state": "Sao Paulo", "raw_ts_rows": 6},
            {"log_date": "2026-07-14", "source": "stream", "country": "US", "state": "California", "raw_ts_rows": 120},
        ]
    )

    result = MODULE.market_rows(frame, ["log_date", "source"])

    states = result[result["market_level"].eq("india_state")].set_index("label")
    countries = result[result["market_level"].eq("country")].set_index("label")
    assert set(states.index) == {"Chhattisgarh", "Unknown / NA"}
    assert set(countries.index) == {"United States"}
    assert countries.loc["United States", "watch_hours"] == 0.2


def test_device_and_os_labels_are_stakeholder_readable() -> None:
    devices = MODULE.canonical_device_labels(pd.Series(["smart_tv", "smartphone", "Unknown Device Type"]))
    systems = MODULE.canonical_os_labels(pd.Series(["Tizen 9", "Android TV 12", "OS Not Exposed In UA"]))

    assert devices.tolist() == ["Smart TV", "Smartphone", "Unknown / NA"]
    assert systems.tolist() == ["Tizen", "Android TV", "Unknown / NA"]


def test_raw_geo_hierarchy_preserves_source_values_without_labels(tmp_path: Path) -> None:
    watch_dir = tmp_path / "watch_hours" / "daily_tables"
    watch_dir.mkdir(parents=True)
    source_rows = [
        {
            "log_date": "2026-07-14",
            "source": "stream",
            "country": "IN",
            "state": "Chattisgarh",
            "city": "NEWDELHI",
            "raw_ts_rows": 60,
            "approx_unique_ips": 4,
        }
    ]
    channel_rows = [{**source_rows[0], "channel_name": "India TV"}]
    pd.DataFrame(source_rows).to_parquet(watch_dir / "geo_daily.parquet", index=False)
    pd.DataFrame(channel_rows).to_parquet(watch_dir / "channel_geo_daily.parquet", index=False)

    source, channel, _ = MODULE.build_raw_geo_hierarchy_daily(
        tmp_path,
        [{"source": "stream", "min_date": "2026-07-14", "max_date": "2026-07-14"}],
    )

    assert source.loc[0, "country"] == "IN"
    assert source.loc[0, "state"] == "Chattisgarh"
    assert source.loc[0, "city"] == "NEWDELHI"
    assert channel.loc[0, "channel_name"] == "India TV"
