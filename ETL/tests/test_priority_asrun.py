from datetime import date
import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
import priority_asrun as asrun
import priority_stream_lake as priority


def test_fast_build_uses_fast_checkpoint_and_isolated_job(tmp_path, monkeypatch):
    monkeypatch.setattr(priority, "ETL", tmp_path)
    evidence = tmp_path / "output/state/downloads/2026-10-10_fast.json"
    evidence.parent.mkdir(parents=True)
    raw = tmp_path / "data/raw/fast"
    raw.mkdir(parents=True)
    evidence.write_text(json.dumps(dict(verified=True, status="complete", date="2026-10-10",
        source="fast", local_count=1, remote_count=1, local_bytes=5, remote_bytes=5, local_path=str(raw))))
    calls = []

    def stage(env, script, output):
        job = json.loads(env["VG_ETL_STAGE_JOBS"])[0]
        assert job["source_key"] == "fast"
        assert job["source_id"] == "fast_2026_10_10"
        calls.append(script)
        if script == "03.py":
            table = pa.table({"reqTimeSec": [1, 2]})
            pq.write_table(table, job["final_clean_file"])
            part = Path(env["VG_ETL_BASE"]) / "lake/source=fast/year=2026/month=10/day=10/part_fast_2026_10_10_0.parquet"
            part.parent.mkdir(parents=True)
            pq.write_table(table, part)

    monkeypatch.setattr(priority, "stage", stage)
    lake = priority.build_day(date(2026, 10, 10), tmp_path / "work", "fast")
    assert lake.exists()
    assert calls == ["001.py", "02.py", "03.py"]


def test_lake_union_keeps_original_and_excludes_future(tmp_path):
    root, target = tmp_path / "lake", tmp_path / "union"
    for day in (9, 10, 11, 12):
        path = root / f"source=fast/year=2026/month=10/day={day:02}/part_fast_0.parquet"
        path.parent.mkdir(parents=True)
        pq.write_table(pa.table({"reqTimeSec": [day]}), path)
    asrun.link_lake(root, target)
    asrun.link_lake(root, target)
    assert len(list(root.rglob("*.parquet"))) == 4
    assert len(list(target.rglob("*.parquet"))) == 3


def test_identity_requires_all_days_and_preserves_history(tmp_path):
    old, new = tmp_path / "old.parquet", tmp_path / "new.parquet"
    rows = [dict(source="fast", log_date="2026-10-08", minute_ist="2026-10-08 00:00:00")]
    pq.write_table(pa.Table.from_pylist(rows), old)
    for source in ("fast", "stream"):
        for day in (9, 10, 11):
            for clock in ("00:00:00", "23:59:00"):
                rows.append(dict(source=source, log_date=f"2026-10-{day:02}", minute_ist=f"2026-10-{day:02} {clock}"))
    pq.write_table(pa.Table.from_pylist(rows), new)
    assert len(asrun.validate_identity(old, new)) == 6
    pq.write_table(pa.Table.from_pylist(rows[:-1]), new)
    with pytest.raises(RuntimeError, match="Partial identity"):
        asrun.validate_identity(old, new)
    pq.write_table(pa.Table.from_pylist(rows[1:]), new)
    with pytest.raises(RuntimeError, match="historical"):
        asrun.validate_identity(old, new)
