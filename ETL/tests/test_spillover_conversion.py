import gzip
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pyarrow.parquet as pq


class SpilloverTest(unittest.TestCase):
    def test_shared_lake_never_modifies_temp_sibling(self):
        spec = importlib.util.spec_from_file_location('spillover_partitioner', Path(__file__).parents[1] / 'src/pipeline/03.py')
        partitioner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(partitioner)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            part = root / 'source=stream/year=2026/month=11/day=01/part_test_0.parquet'
            temp = root / 'Temp/work/part_test_0.parquet'
            for path in (part, temp):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'preserve')
            with patch.object(partitioner, 'LAKE_FOLDER', root):
                self.assertEqual(list(partitioner.lake_partition_files('part_test_*.parquet')), [part])
                self.assertEqual(partitioner.remove_previous_partitions('part_test'), 1)
                partitioner.prune_empty_dirs()
                self.assertTrue(temp.exists())

    def test_window_boundaries_and_normal_conversion(self):
        spec = importlib.util.spec_from_file_location('spillover_converter', Path(__file__).parents[1] / 'src/pipeline/001.py')
        converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(converter)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / 'input.gz'
            with gzip.open(raw, 'wt') as handle:
                for epoch in [99, 100, 199, 200]:
                    handle.write(json.dumps(dict(reqTimeSec=str(epoch))) + '\n')
            task = dict(out_path=str(root / 'filtered.parquet'), files=[str(raw)],
                        compression='snappy', row_buffer=2, row_group_size=2,
                        add_meta=False, placeholders=[], cols_to_keep=['reqTimeSec'])
            with patch.dict(os.environ, {'VG_ETL_ROW_START_EPOCH': '100', 'VG_ETL_ROW_END_EPOCH': '200'}):
                result = converter._convert_batch(task)
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(pq.read_table(task['out_path'])['reqTimeSec'].to_pylist(), ['100', '199'])
            task['out_path'] = str(root / 'normal.parquet')
            with patch.dict(os.environ, {'VG_ETL_ROW_START_EPOCH': '', 'VG_ETL_ROW_END_EPOCH': ''}):
                result = converter._convert_batch(task)
                self.assertEqual(result['rows'], 4)


if __name__ == '__main__':
    unittest.main()
