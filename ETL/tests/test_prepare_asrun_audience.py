import tempfile
import unittest
from pathlib import Path

import pandas as pd

from ETL.src.tools.prepare_asrun_audience import prepare


class PrepareAudienceTests(unittest.TestCase):
    def test_replaces_whole_days_preserves_history_and_rejects_partial(self):
        def day(source, date, count, value):
            return pd.DataFrame({
                'source': source, 'log_date': date,
                'minute_ist': pd.date_range(date, periods=count, freq='min').astype(str),
                'distinct_cliips': value,
            })
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = pd.concat([day('fast', '2026-11-08', 1440, 1),
                                  day('stream', '2026-11-08', 1440, 2)])
            current = pd.concat([day('fast', '2026-11-08', 1440, 3),
                                 day('stream', '2026-11-08', 330, 99),
                                 day('stream', '2026-11-15', 1440, 4),
                                 day('fast', '2026-11-16', 330, 99)])
            baseline.to_parquet(root / 'old.parquet', index=False)
            current.to_parquet(root / 'new.parquet', index=False)
            prepare(root / 'old.parquet', root / 'new.parquet', root / 'out.parquet')
            result = pd.read_parquet(root / 'out.parquet')
            self.assertEqual(len(result), 4320)
            self.assertEqual(result.groupby(['source', 'log_date']).distinct_cliips.first().to_dict(), {
                ('fast', '2026-11-08'): 3,
                ('stream', '2026-11-08'): 2,
                ('stream', '2026-11-15'): 4,
            })
            self.assertFalse(result.duplicated(['source', 'log_date', 'minute_ist']).any())


if __name__ == '__main__':
    unittest.main()
