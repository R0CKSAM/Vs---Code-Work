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
