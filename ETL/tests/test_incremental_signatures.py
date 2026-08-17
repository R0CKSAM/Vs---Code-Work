from __future__ import annotations

import sys
from pathlib import Path

ETL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_ROOT))

from src.overview.deviceSnapshotGenerator import comparable_day_signature
from src.tools.build_identity_mart import comparable_partition_signature
from src.tools.build_latency_profile_incremental import comparable_signature


def test_latency_signature_ignores_physical_path() -> None:
    archived = {
        "file_count": 1,
        "total_bytes": 123,
        "max_mtime_ns": 456,
        "files": [{"path": "Z:/archive/day/part.parquet", "name": "part.parquet", "bytes": 123, "mtime_ns": 456}],
    }
    hot = {
        "file_count": 1,
        "total_bytes": 123,
        "max_mtime_ns": 456,
        "files": [{"name": "part.parquet", "bytes": 123, "mtime_ns": 456}],
    }
    assert comparable_signature(archived) == comparable_signature(hot)
    hot["total_bytes"] = 124
    assert comparable_signature(archived) != comparable_signature(hot)


def test_identity_signature_ignores_lake_root_and_partition_path() -> None:
    archived = {
        "source": "fast",
        "date": "2026-08-14",
        "lake_root": "Z:/archive",
        "partition_path": "Z:/archive/source=fast/day=14",
        "file_count": 1,
        "bytes": 123,
        "max_mtime_ns": 456,
        "files": [{"path": "Z:/archive/part.parquet", "name": "part.parquet", "bytes": 123, "mtime_ns": 456}],
    }
    hot = {
        "source": "fast",
        "date": "2026-08-14",
        "file_count": 1,
        "bytes": 123,
        "max_mtime_ns": 456,
        "files": [{"name": "part.parquet", "bytes": 123, "mtime_ns": 456}],
    }
    assert comparable_partition_signature(archived) == comparable_partition_signature(hot)


def test_device_signature_ignores_roots_only() -> None:
    archived = {"files": 2, "bytes": 123, "rows": 10, "roots": ["Z:/archive"], "sources": ["fast"]}
    hot = {"files": 2, "bytes": 123, "rows": 10, "sources": ["fast"]}
    assert comparable_day_signature(archived) == comparable_day_signature(hot)
    hot["rows"] = 11
    assert comparable_day_signature(archived) != comparable_day_signature(hot)
