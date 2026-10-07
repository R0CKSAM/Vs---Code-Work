import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

spec=importlib.util.spec_from_file_location('archive_tool',Path(__file__).resolve().parents[1]/'src/tools/archive_lake_partitions.py')
archive=importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ArchiveCopySafetyTest(unittest.TestCase):
    def test_verified_copy_keeps_source_until_caller_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.parquet'
            destination=Path(folder)/'archive/result.parquet'
            pq.write_table(pa.table({'reqTimeSec':[1.0,2.0]}),source)
            result=archive.copy_verified(source,destination,True)
            self.assertTrue(source.exists())
            self.assertEqual(result['sha256'],archive.sha256(destination))
            self.assertFalse(destination.with_name(destination.name+'.archiving').exists())

    def test_bad_checksum_never_removes_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.parquet'
            destination=Path(folder)/'archive/result.parquet'
            pq.write_table(pa.table({'reqTimeSec':[1.0,2.0]}),source)
            with patch.object(archive,'sha256',side_effect=['original','different']):
                with self.assertRaises(RuntimeError):
                    archive.copy_verified(source,destination,True)
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
