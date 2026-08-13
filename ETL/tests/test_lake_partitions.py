from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ETL.src.common.lake_partitions import discover_partitions, parquet_globs


TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / "output" / "cache" / "test_tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def write_part(root: Path, source: str, day: date, name: str, rows: int) -> Path:
    folder = (
        root
        / f"source={source}"
        / f"year={day.year:04d}"
        / f"month={day.month:02d}"
        / f"day={day.day:02d}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    pq.write_table(pa.table({"value": list(range(rows))}), path)
    return path


class LakePartitionTests(unittest.TestCase):
    def test_merges_complementary_files_across_roots(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            hot = Path(temp) / "hot"
            archive = Path(temp) / "archive"
            day = date(2026, 8, 12)
            tail = write_part(archive, "fast", day, "part_fast_2026_08_11_0.parquet", 2)
            current = write_part(hot, "fast", day, "part_fast_2026_08_12_0.parquet", 3)

            partitions = discover_partitions([hot, archive], source="fast", start=day, end=day)

            self.assertEqual(len(partitions), 1)
            self.assertEqual(set(partitions[0].files), {tail, current})
            self.assertEqual(set(parquet_globs(partitions)), {
                str(tail).replace("\\", "/"),
                str(current).replace("\\", "/"),
            })

    def test_repeated_filename_is_selected_once(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            hot = Path(temp) / "hot"
            archive = Path(temp) / "archive"
            day = date(2026, 8, 12)
            write_part(hot, "stream", day, "part_stream_2026_08_12_0.parquet", 2)
            better = write_part(archive, "stream", day, "part_stream_2026_08_12_0.parquet", 4)

            partitions = discover_partitions([hot, archive], source="stream", start=day, end=day)

            self.assertEqual(partitions[0].files, (better,))


if __name__ == "__main__":
    unittest.main()
