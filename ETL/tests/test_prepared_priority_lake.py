import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
import prepared_priority_lake as prepared


def test_adopt_and_verify_without_duplicate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(prepared, "ETL", tmp_path)
    roots = {s: tmp_path / s for s in ("fast", "stream")}
    base = tmp_path / "data"
    checkpoints = tmp_path / "output/state/downloads"
    checkpoints.mkdir(parents=True)
    for source, root in roots.items():
        root.mkdir()
        state = "asrun_state.json" if source == "fast" else "priority_state.json"
        (root / state).write_text(json.dumps(dict(status="complete")))
        for day in ("2026-10-10", "2026-10-11"):
            run = root / day
            run.mkdir()
            name = source + "_" + day.replace("-", "_")
            table = pa.table({"reqTimeSec": [1, 2]})
            pq.write_table(table, run / f"{name}_final_clean.parquet")
            part = run / f"lake/source={source}/year=2026/month=10/day={day[-2:]}/part_{name}_0.parquet"
            part.parent.mkdir(parents=True)
            pq.write_table(table, part)
            (checkpoints / f"{day}_{source}.json").write_text("{}")
    prepared.adopt(roots, base)
    receipt = tmp_path / "output/state/prepared_lake/2026-10-10.json"
    assert prepared.verify(receipt, base)["date"] == "2026-10-10"
    (checkpoints / "2026-10-10_fast.json").write_text('{"changed":true}')
    with pytest.raises(RuntimeError, match="checkpoint changed"):
        prepared.verify(receipt, base)


def test_link_refuses_overwrite(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"new")
    b.write_bytes(b"old")
    with pytest.raises(RuntimeError, match="conflicting"):
        prepared.link_verified(a, b)
    assert b.read_bytes() == b"old"
