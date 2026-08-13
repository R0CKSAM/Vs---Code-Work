from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "tools"
sys.path.insert(0, str(TOOLS_DIR))
TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / "output" / "cache" / "test_tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

import validate_daily_delivery as validator  # noqa: E402


IST = ZoneInfo("Asia/Kolkata")


def epoch(value: str) -> float:
    return datetime.fromisoformat(value).replace(tzinfo=IST).timestamp()


def write_part(root: Path, source: str, day: date, name: str, values: list[float]) -> Path:
    folder = (
        root
        / f"source={source}"
        / f"year={day.year:04d}"
        / f"month={day.month:02d}"
        / f"day={day.day:02d}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    pq.write_table(pa.table({"reqTimeSec": values}), path)
    return path


class DailyDeliveryValidationTests(unittest.TestCase):
    def test_full_day_passes(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            day = date(2026, 8, 9)
            write_part(
                root,
                "fast",
                day,
                "part_fast.parquet",
                [epoch("2026-08-09T00:00:00"), epoch("2026-08-09T23:59:59")],
            )
            result = validator.source_result([root], "fast", day, 15, 15, 30)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["hard_failure"])

    def test_partial_day_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            day = date(2026, 8, 7)
            write_part(
                root,
                "stream",
                day,
                "part_stream.parquet",
                [epoch("2026-08-07T00:00:00"), epoch("2026-08-07T05:29:59")],
            )
            result = validator.source_result([root], "stream", day, 15, 15, 30)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(result["hard_failure"])

    def test_large_overlap_is_duplicate(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            day = date(2026, 8, 10)
            write_part(
                root,
                "stream",
                day,
                "part_1.parquet",
                [epoch("2026-08-10T00:00:00"), epoch("2026-08-10T05:30:00")],
            )
            write_part(
                root,
                "stream",
                day,
                "part_2.parquet",
                [epoch("2026-08-10T00:10:00"), epoch("2026-08-10T23:59:59")],
            )
            result = validator.source_result([root], "stream", day, 15, 15, 30)
            self.assertEqual(result["status"], "DUPLICATE")

    def test_complete_archive_beats_partial_primary(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            primary = Path(temp) / "primary"
            archive = Path(temp) / "archive"
            day = date(2026, 7, 31)
            write_part(
                primary,
                "fast",
                day,
                "part_partial.parquet",
                [epoch("2026-07-31T00:00:00"), epoch("2026-07-31T05:29:59")],
            )
            write_part(
                archive,
                "fast",
                day,
                "part_full.parquet",
                [epoch("2026-07-31T00:00:00"), epoch("2026-07-31T23:59:59")],
            )
            result = validator.source_result([primary, archive], "fast", day, 15, 15, 30)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(Path(result["selected"]["root"]), archive)

    def test_channel_outage_uses_canonical_daily_mart(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            profile = Path(temp) / "watch_hours" / "profile"
            daily = profile.parent / "daily_tables"
            daily.mkdir(parents=True)
            rows = [
                {
                    "log_date": f"2026-08-0{day}",
                    "source": "stream",
                    "channel_name": "India TV",
                    "raw_ts_chunks": 10000,
                }
                for day in range(4, 9)
            ]
            rows.append(
                {
                    "log_date": "2026-08-09",
                    "source": "stream",
                    "channel_name": "India TV",
                    "raw_ts_chunks": 100,
                }
            )
            pd.DataFrame(rows).to_parquet(daily / "channel_audience_daily.parquet", index=False)
            anomalies, warnings = validator.channel_anomalies(
                profile,
                date(2026, 8, 9),
                ["stream"],
                baseline_days=28,
                threshold_pct=5,
                min_baseline_days=3,
                min_median_rows=1000,
            )
            self.assertFalse(warnings)
            self.assertEqual(len(anomalies), 1)
            self.assertEqual(anomalies[0]["channel"], "India TV")


if __name__ == "__main__":
    unittest.main()
