import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/tools'))
from export_sony_bravia_weekly import (
    IST, collect_partition, initialize_matched, is_bravia, pct_change,
    summaries, verify_partitions,
)


class BraviaReportTests(unittest.TestCase):
    def test_cohort_and_zero_baseline(self):
        self.assertTrue(is_bravia('Android%20BRAVIA%204K'))
        self.assertTrue(is_bravia('opaque player', 'BRAVIA VU3'))
        self.assertFalse(is_bravia('Sony Xperia', 'Xperia 1'))
        self.assertFalse(is_bravia('Sony PlayStation', 'PS5'))
        self.assertIsNone(pct_change(10, 0))
        self.assertEqual(pct_change(15, 10), 50)

    def test_missing_day_is_not_zero(self):
        part = SimpleNamespace(source='stream', date_text='2026-10-02')
        with self.assertRaises(ValueError):
            verify_partitions([part], ['stream', 'fast'], dt.date(2026, 10, 2), dt.date(2026, 10, 2))

    def test_request_filter_and_exact_unions(self):
        con = duckdb.connect()
        con.execute("CREATE TEMP TABLE bravia_alias(ua_raw VARCHAR, model VARCHAR)")
        con.execute("INSERT INTO bravia_alias VALUES ('BRAVIA A', 'BRAVIA A')")
        initialize_matched(con)
        midnight = dt.datetime(2026, 10, 9, tzinfo=IST).timestamp()
        data = pd.DataFrame([
            ['BRAVIA A', 'ip1', 'device_id=abc', '200', '/a.ts', midnight],
            ['BRAVIA A', 'ip1', 'device_id=abc', '500', '/a.ts', midnight+5],
            ['BRAVIA A', 'ip2', 'device_id=null', '200', '/a.ts', midnight+10],
            ['BRAVIA new', 'ip2', '', '200', '/b.ts', midnight+12],
            ['Sony Xperia', 'ip3', 'device_id=phone', '200', '/a.ts', midnight+15],
            ['BRAVIA A', 'ip4', 'device_id=tomorrow', '200', '/a.ts', midnight+86400],
            ['BRAVIA A', 'ip5', 'device_id=manifest', '200', '/a.m3u8', midnight],
        ], columns=['UA','cliIP','queryStr','statusCode','reqPath','reqTimeSec'])
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'part.parquet'
            data.to_parquet(file,index=False)
            collect_partition(con, 'stream', '2026-10-09', [file])
        con.execute("INSERT INTO matched VALUES ('stream','2026-10-10','BRAVIA A','ip1','abc',2,2,0,0)")
        result = summaries(con, ['stream', 'fast'], dt.date(2026,10,2), dt.date(2026,10,9), dt.date(2026,10,15))
        current = result['weekly'].query("source == 'stream' and period == 'current'").iloc[0]
        self.assertEqual(current.segment_requests, 6)
        self.assertEqual(current.distinct_client_ips, 2)
        self.assertEqual(current.distinct_reported_device_ids, 1)
        self.assertEqual(current.requests_with_device_id, 4)
        self.assertAlmostEqual(current.estimated_raw_watch_hours, 6/600)
        self.assertAlmostEqual(current.estimated_http200_watch_hours, 5/600)
        self.assertEqual(len(result['daily']), 28)
        con.close()


if __name__ == '__main__':
    unittest.main()
