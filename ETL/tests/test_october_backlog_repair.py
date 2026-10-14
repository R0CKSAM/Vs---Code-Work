import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

SCRIPT = Path(__file__).resolve().parents[1] / 'src/tools/repair_october_backlog_20261014.py'
spec = importlib.util.spec_from_file_location('october_repair', SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def table(old, new):
    return pa.table({'source': ['fast', 'fast'], 'log_date': ['2026-10-08', '2026-10-09'], 'raw_ts_rows': [old, new]})


class RepairTest(unittest.TestCase):
    def scenario(self, old, new, fails):
        root = SCRIPT.parents[2] / 'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            work = Path(folder)
            mart = work / 'mart'
            mart.mkdir()
            filename = 'fast_platform_channel_ua_device_daily.parquet'
            target = mart / filename
            pq.write_table(table(5, 7), target)
            pq.write_table(table(5, 20), mart / 'concurrency_minute.parquet')
            original = target.read_bytes()

            def fake_run(name, args):
                pq.write_table(table(old, new), work / name / filename)

            with patch.multiple(repair, WORK=work, MART=mart, STATE=work/'state.json', COMPLETED=[]), patch.object(repair, 'run', fake_run), patch.object(repair.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 40*1024**3})()):
                if fails:
                    with self.assertRaises(RuntimeError):
                        repair.repair('2026-10-09', filename, 'build_fast_platform_channel_ua_device')
                    self.assertEqual(original, target.read_bytes())
                else:
                    repair.repair('2026-10-09', filename, 'build_fast_platform_channel_ua_device')
                    self.assertEqual(pq.ParquetFile(target).read()['raw_ts_rows'].to_pylist(), [5, 20])

    def test_validated_day_publishes(self):
        self.scenario(5, 20, False)

    def test_changed_history_keeps_live_file(self):
        self.scenario(6, 20, True)

    def test_mismatched_totals_keeps_live_file(self):
        self.scenario(5, 19, True)

    def test_resume_revalidates_completed_day(self):
        root = SCRIPT.parents[2] / 'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            work = Path(folder)
            filename = 'device.parquet'
            pq.write_table(table(5, 20), work / filename)
            pq.write_table(table(5, 20), work / 'concurrency_minute.parquet')
            completed = [dict(date='2026-10-09', step='build_fast_platform_channel_ua_device')]
            with patch.multiple(repair, WORK=work, MART=work, STATE=work/'state.json', COMPLETED=completed, RESUME=True), patch.object(repair, 'run') as run:
                repair.repair('2026-10-09', filename, 'build_fast_platform_channel_ua_device')
                run.assert_not_called()
                pq.write_table(table(5, 19), work / filename)
                with self.assertRaisesRegex(RuntimeError, 'no longer validates'):
                    repair.repair('2026-10-09', filename, 'build_fast_platform_channel_ua_device')


if __name__ == '__main__':
    unittest.main()
