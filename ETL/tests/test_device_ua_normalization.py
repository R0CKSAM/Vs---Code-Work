import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ETL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL / 'src/tools'))
import build_fast_platform_channel_ua_device as builder


class DeviceNormalizationTest(unittest.TestCase):
    def test_malformed_encoded_and_null_values_preserve_rows(self):
        root = ETL / 'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder, duckdb.connect() as con:
            con.execute('SET threads=1')
            raw = Path(folder) / 'raw.parquet'
            uas = ['Agent+X', 'Agent%2520X', 'Agent%20X', '%FF%FE', None, '']
            n = len(uas)
            pq.write_table(pa.table(dict(UA=pa.array(uas, type=pa.string()), source=['fast']*n,
                reqPath=['/channel/segment.ts']*n, reqHost=['example.test']*n,
                cliIP=['test-ip']*n, statusCode=['200']*n,
                reqTimeSec=[datetime(2026,10,10,12,tzinfo=timezone.utc).timestamp()]*n)), raw)
            lookup = Path(folder) / 'lookup.parquet'
            values = {column: pa.array([None], type=pa.string()) for column in builder.LOOKUP_COLUMNS}
            values['ua_norm'] = pa.array(['Agent X'])
            values['decode_status'] = pa.array(['decoded_api'])
            pq.write_table(pa.table(values), lookup)
            con.execute('CREATE TABLE host_map(reqHost VARCHAR, host_channel_name VARCHAR)')
            con.execute('CREATE TABLE path_map(candidate_id VARCHAR, path_channel_name VARCHAR)')
            args = Namespace(start='2026-10-10', end='2026-10-10', source='fast', ua_lookup=lookup,
                             selected_lake_files=[raw])
            with patch.object(builder, 'configure_lake_selection'), patch.object(builder, 'date_filter_sql', return_value='1=1'):
                builder.build_device_table(con, args)
            normalized = dict(con.execute('SELECT * FROM ua_normalization_map').fetchall())
            self.assertEqual(normalized['Agent%2520X'], 'Agent X')
            self.assertEqual(normalized['Agent+X'], 'Agent X')
            self.assertEqual(normalized['%FF%FE'], '\ufffd\ufffd')
            self.assertIsNone(normalized[''])
            self.assertEqual(con.execute('SELECT sum(raw_ts_rows), sum(status_200_ts_rows) FROM fast_platform_channel_ua_device_new').fetchone(), (6,6))
            self.assertEqual(con.execute("SELECT raw_ts_rows,distinct_uas,approx_unique_ips FROM fast_platform_channel_ua_device_new WHERE decode_status='decoded_api'").fetchone(), (3,1,1))

    def test_empty_normalization_map_has_string_columns(self):
        root = ETL / 'output/temp/tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder, duckdb.connect() as con:
            raw = Path(folder) / 'empty.parquet'
            pq.write_table(pa.table({'UA': pa.array([None], type=pa.string())}), raw)
            count = builder.ensure_ua_normalization_map(con, builder.parquet_source_sql([raw]), '1=1')
            self.assertEqual(count, 0)
            self.assertEqual([r[1] for r in con.execute('DESCRIBE ua_normalization_map').fetchall()], ['VARCHAR','VARCHAR'])


if __name__ == '__main__':
    unittest.main()
