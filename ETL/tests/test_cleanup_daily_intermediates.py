from __future__ import annotations

import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCRIPT = Path(__file__).resolve().parents[1] / "src" / "tools" / "cleanup_daily_intermediates.py"
TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / "output" / "temp" / "tests"


class CleanupDailyIntermediatesTest(unittest.TestCase):
    def test_dry_run_then_validated_cleanup(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            base = root / "data"
            lake = base / "lake"
            raw_root = base / "raw" / "Veto Logs Backup"
            audit = root / "audit"
            target = "2026-08-13"

            final_file = (
                base
                / "stage"
                / "final_clean"
                / "source=stream"
                / "year=2026"
                / "month=08"
                / "day=13"
                / "stream_2026_08_13_final_clean.parquet"
            )
            stage_file = (
                base
                / "stage"
                / "parquet"
                / "source=stream"
                / "year=2026"
                / "month=08"
                / "day=13"
                / "part-0.parquet"
            )
            lake_file = (
                lake
                / "source=stream"
                / "year=2026"
                / "month=08"
                / "day=13"
                / "part_stream_2026_08_13_0.parquet"
            )
            late_lake_file = (
                lake
                / "source=stream"
                / "year=2026"
                / "month=08"
                / "day=04"
                / "part_stream_2026_08_13_0.parquet"
            )
            raw_file = raw_root / "Veto Stream Backup" / "08" / "13" / "sample.log.gz"
            diagnostic_file = stage_file.parent / "conversion_errors.csv"
            for path in (final_file, stage_file, lake_file, late_lake_file, raw_file):
                path.parent.mkdir(parents=True, exist_ok=True)

            table = pa.table({"value": [1, 2, 3]})
            pq.write_table(pa.table({"value": [1, 2, 3, 4]}), final_file)
            for path in (stage_file, lake_file):
                pq.write_table(table, path)
            pq.write_table(pa.table({"value": [4]}), late_lake_file)
            with gzip.open(raw_file, "wt", encoding="utf-8") as handle:
                handle.write("sample\n")
            diagnostic_file.write_text("file,error\n", encoding="utf-8")

            validation = root / "validation.json"
            validation.write_text(
                json.dumps(
                    {
                        "mode": "full",
                        "date": target,
                        "overall_status": "PASS",
                        "hard_failure_count": 0,
                        "source_results": [
                            {
                                "source": "stream",
                                "status": "PASS",
                                "selected": {"full_day": True},
                            }
                        ],
                        "profile_reconciliation": [
                            {"source": "stream", "status": "PASS", "delta_rows": 0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            command = [
                sys.executable,
                str(SCRIPT),
                "--base",
                str(base),
                "--lake",
                str(lake),
                "--raw-root",
                str(raw_root),
                "--date",
                target,
                "--sources",
                "stream",
                "--validation-report",
                str(validation),
                "--audit-dir",
                str(audit),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertTrue(final_file.exists())
            self.assertTrue(stage_file.exists())
            self.assertTrue(raw_file.exists())

            subprocess.run(command + ["--execute"], check=True, capture_output=True, text=True)
            self.assertFalse(final_file.exists())
            self.assertFalse(stage_file.exists())
            self.assertFalse(raw_file.exists())
            self.assertTrue(lake_file.exists())
            self.assertTrue(late_lake_file.exists())
            self.assertTrue(diagnostic_file.exists())

            manifests = sorted(audit.glob("cleanup_*.json"))
            self.assertEqual(len(manifests), 2)
            completed = json.loads(manifests[-1].read_text(encoding="utf-8"))
            self.assertEqual(completed["status"], "complete")
            self.assertEqual(completed["deleted_count"], 3)

    def test_archive_lake_and_etl_state_can_replace_removed_final_clean(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            base = root / "data"
            lake = base / "lake"
            archive_lake = root / "archive_lake"
            raw_root = base / "raw" / "Veto Logs Backup"
            audit = root / "audit"
            target = "2026-08-03"
            source_id = "stream_2026_08_03"

            lake.mkdir(parents=True)
            lake_file = (
                archive_lake
                / "source=stream"
                / "year=2026"
                / "month=08"
                / "day=03"
                / f"part_{source_id}_0.parquet"
            )
            raw_file = raw_root / "Veto Stream Backup" / "08" / "03" / "sample.log.gz"
            lake_file.parent.mkdir(parents=True)
            raw_file.parent.mkdir(parents=True)
            pq.write_table(pa.table({"value": [1, 2, 3]}), lake_file)
            with gzip.open(raw_file, "wt", encoding="utf-8") as handle:
                handle.write("sample\n")

            state = root / "etl3_state.json"
            state.write_text(
                json.dumps(
                    {
                        f"{source_id}_final_clean.parquet": {
                            "status": "ok",
                            "source_key": "stream",
                            "rows": 3,
                        }
                    }
                ),
                encoding="utf-8",
            )
            validation = root / "validation.json"
            validation.write_text(
                json.dumps(
                    {
                        "mode": "full",
                        "date": target,
                        "overall_status": "PASS",
                        "hard_failure_count": 0,
                        "source_results": [
                            {
                                "source": "stream",
                                "status": "PASS",
                                "selected": {"full_day": True},
                            }
                        ],
                        "profile_reconciliation": [
                            {"source": "stream", "status": "PASS", "delta_rows": 0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            command = [
                sys.executable,
                str(SCRIPT),
                "--base",
                str(base),
                "--lake",
                str(lake),
                "--archive-lake",
                str(archive_lake),
                "--etl3-state",
                str(state),
                "--raw-root",
                str(raw_root),
                "--date",
                target,
                "--sources",
                "stream",
                "--validation-report",
                str(validation),
                "--audit-dir",
                str(audit),
                "--execute",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertFalse(raw_file.exists())
            self.assertTrue(lake_file.exists())
            completed = json.loads(next(audit.glob("cleanup_*.json")).read_text(encoding="utf-8"))
            self.assertEqual(completed["checks"][0]["evidence_type"], "etl3_state")


if __name__ == "__main__":
    unittest.main()
