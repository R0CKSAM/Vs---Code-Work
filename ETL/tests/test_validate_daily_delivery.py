from __future__ import annotations

import sys
import json
import tempfile
import unittest
from unittest.mock import patch
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
    def test_channel_confirmation_never_overrides_source_failure(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp:
            root = Path(tmp)
            review = root / "review.json"
            review.write_text(json.dumps({"date": "2026-10-19", "confirmed_by": "operator", "channels": [
                {"source": "stream", "channel": "Event", "target_raw_ts_chunks": 0, "reason": "Off air"}]}))
            row = dict(source="stream", channel="Event", date="2026-10-19", target_raw_ts_chunks=0)
            argv = ["validate", "--lake", str(root), "--date", "2026-10-19", "--sources", "stream",
                    "--profile-dir", str(root), "--output-dir", str(root), "--channel-review-file", str(review)]
            failed = dict(source="stream", status="PARTIAL", hard_failure=True,
                          selected=None, candidates=[], message="Missing hours")
            with patch.object(sys, "argv", argv), patch.object(validator, "archive_roots", return_value=[]), \
                 patch.object(validator, "source_result", return_value=failed), \
                 patch.object(validator, "reconcile_profile", return_value=[]), \
                 patch.object(validator, "channel_anomalies", return_value=([row], [])):
                with self.assertRaises(SystemExit) as raised:
                    validator.main()
            self.assertEqual(raised.exception.code, 2)
            report = json.loads((root / "daily_delivery_validation_latest.json").read_text())
            self.assertEqual(report["overall_status"], "FAIL")
            self.assertEqual(len(report["acknowledged_channels"]), 1)

    def test_operator_review_matches_only_exact_date_channel_and_count(self):
        day = date(2026, 10, 19)
        row = dict(source="stream", channel="UP Government Live", date=str(day), target_raw_ts_chunks=0)
        review = dict(date=str(day), confirmed_by="test operator", channels=[
            dict(source="stream", channel=row["channel"], target_raw_ts_chunks=0, reason="No broadcast")])
        remaining, accepted, warnings = validator.apply_channel_review([row], day, review)
        self.assertEqual(remaining, [])
        self.assertEqual(accepted[0]["status"], "OPERATOR_CONFIRMED")
        self.assertEqual(warnings, [])
        self.assertNotIn("reason", row)
        for change in ({"target_raw_ts_chunks": 1}, {"source": "fast"}, {"channel": "Other"}, {"date": "2026-10-18"}):
            observed = {**row, **change}
            remaining, accepted, warnings = validator.apply_channel_review([observed], day, review)
            self.assertEqual(remaining, [observed])
            self.assertEqual(accepted, [])
            self.assertTrue(warnings)
        with self.assertRaises(ValueError):
            validator.apply_channel_review([row], date(2026, 10, 20), review)
        review["channels"].append(review["channels"][0])
        with self.assertRaises(ValueError):
            validator.apply_channel_review([row], day, review)

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

    def test_file_time_overlap_alone_is_not_duplicate_proof(self) -> None:
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
            self.assertEqual(result["status"], "PASS")

    def test_complementary_hot_and_archive_files_are_merged(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            primary = Path(temp) / "primary"
            archive = Path(temp) / "archive"
            day = date(2026, 8, 12)
            write_part(
                archive,
                "fast",
                day,
                "part_fast_2026_08_11_0.parquet",
                [epoch("2026-08-12T00:00:00"), epoch("2026-08-12T05:29:59")],
            )
            write_part(
                primary,
                "fast",
                day,
                "part_fast_2026_08_12_0.parquet",
                [epoch("2026-08-12T05:20:00"), epoch("2026-08-12T23:59:59")],
            )
            result = validator.source_result([primary, archive], "fast", day, 15, 15, 30)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["selected"]["files"]), 2)

    def test_complete_archive_beats_partial_primary(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            primary = Path(temp) / "primary"
            archive = Path(temp) / "archive"
            day = date(2026, 7, 31)
            write_part(
                primary,
                "fast",
                day,
                "part_fast_2026_07_31_0.parquet",
                [epoch("2026-07-31T00:00:00"), epoch("2026-07-31T05:29:59")],
            )
            write_part(
                archive,
                "fast",
                day,
                "part_fast_2026_07_31_0.parquet",
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

    def test_event_channel_is_not_treated_as_daily_outage(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            profile = Path(temp) / "watch_hours" / "profile"
            daily = profile.parent / "daily_tables"
            daily.mkdir(parents=True)
            rows = []
            for day in range(1, 10):
                rows.append({
                    "log_date": f"2026-08-{day:02d}",
                    "source": "stream",
                    "channel_name": "India TV",
                    "raw_ts_chunks": 10000,
                })
            rows.append({
                "log_date": "2026-08-10",
                "source": "stream",
                "channel_name": "India TV",
                "raw_ts_chunks": 10000,
            })
            for day in range(1, 10):
                rows.append({
                    "log_date": f"2026-08-{day:02d}",
                    "source": "stream",
                    "channel_name": "Veto Cricket Live",
                    "raw_ts_chunks": 3000,
                })
            pd.DataFrame(rows).to_parquet(daily / "channel_audience_daily.parquet", index=False)

            expected_inactive = []
            anomalies, warnings = validator.channel_anomalies(
                profile,
                date(2026, 8, 10),
                ["stream"],
                baseline_days=28,
                threshold_pct=5,
                min_baseline_days=3,
                min_median_rows=1000,
                expected_inactive=expected_inactive,
            )

            self.assertFalse(warnings)
            self.assertEqual(anomalies, [])
            self.assertEqual(len(expected_inactive), 1)
            self.assertEqual(expected_inactive[0]["channel"], "Veto Cricket Live")
            self.assertEqual(expected_inactive[0]["status"], "EXPECTED_INACTIVE")


if __name__ == "__main__":
    unittest.main()
