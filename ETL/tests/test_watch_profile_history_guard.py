from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


ETL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_ROOT))
TEST_TEMP_ROOT = ETL_ROOT / "output" / "temp" / "tests"

from src.orchestrator.run_pipeline import _profile_covers_lake_history


class WatchProfileHistoryGuardTest(unittest.TestCase):
    def test_rejects_profile_that_starts_after_archived_lake(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            profile = root / "profile"
            profile.mkdir()
            pq.write_table(
                pa.table({"log_date": ["2026-08-01", "2026-08-02"]}),
                profile / "daily_volume.parquet",
            )
            (root / "archive" / "source=stream" / "year=2026" / "month=03" / "day=25").mkdir(
                parents=True
            )

            self.assertFalse(_profile_covers_lake_history(profile, [root / "archive"]))

    def test_accepts_profile_covering_earliest_lake_day(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            profile = root / "profile"
            profile.mkdir()
            pq.write_table(
                pa.table({"log_date": ["2026-03-25", "2026-08-01"]}),
                profile / "daily_volume.parquet",
            )
            (root / "archive" / "source=stream" / "year=2026" / "month=03" / "day=25").mkdir(
                parents=True
            )

            self.assertTrue(_profile_covers_lake_history(profile, [root / "archive"]))


if __name__ == "__main__":
    unittest.main()
