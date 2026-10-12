from datetime import date
import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "tools"))
import priority_stream_lake as priority


def write_part(root, day, values):
    path = root / "source=stream" / "year=2026" / "month=10" / f"day={day:02}" / "part_stream_2026_10_11_0.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"reqTimeSec": values}), path)
    return path


def test_publish_verifies_and_retains_source(tmp_path):
    source = write_part(tmp_path / "lake", 11, [1, 2, 3])
    records = []
    priority.publish(tmp_path / "lake", tmp_path / "archive", date(2026, 10, 11), records)
    assert source.exists()
    assert records[0]["verification"]["metadata"]["rows"] == 3
    assert records[0]["verification"]["sha256"]
    priority.publish(tmp_path / "lake", tmp_path / "archive", date(2026, 10, 11), records)
    assert records[-1]["action"] == "already_identical"


def test_publish_refuses_conflicting_destination(tmp_path):
    write_part(tmp_path / "lake", 11, [1, 2, 3])
    destination = write_part(tmp_path / "archive", 11, [8, 9])
    before = destination.read_bytes()
    with pytest.raises(RuntimeError, match="refusing overwrite"):
        priority.publish(tmp_path / "lake", tmp_path / "archive", date(2026, 10, 11), [])
    assert destination.read_bytes() == before


def test_future_spill_is_not_published(tmp_path):
    write_part(tmp_path / "lake", 12, [1, 2])
    records = []
    priority.publish(tmp_path / "lake", tmp_path / "archive", date(2026, 10, 11), records)
    assert records == []
    assert not (tmp_path / "archive").exists()


def test_unverified_download_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(priority, "ETL", tmp_path)
    evidence = tmp_path / "output" / "state" / "downloads" / "2026-10-10_stream.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(json.dumps({"verified": False}))
    with pytest.raises(RuntimeError, match="verified download"):
        priority.build_day(date(2026, 10, 10), tmp_path / "work")


def test_fast_publish_is_copy_only_and_checkpoints(tmp_path):
    lake = tmp_path / "lake"
    fast = lake / "source=fast/year=2026/month=10/day=11/part_fast_0.parquet"
    fast.parent.mkdir(parents=True)
    pq.write_table(pa.table({"reqTimeSec": [1, 2, 3]}), fast)
    write_part(lake, 11, [4, 5])
    records, checkpoints = [], []
    priority.publish(lake, tmp_path / "archive", date(2026, 10, 11), records,
                     "fast", lambda: checkpoints.append(len(records)))
    assert fast.exists()
    assert len(records) == 1
    assert checkpoints == [1]
    assert not (tmp_path / "archive/source=stream").exists()
