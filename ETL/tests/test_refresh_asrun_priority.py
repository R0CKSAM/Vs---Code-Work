import importlib.util
from pathlib import Path
import sys

import duckdb
import pytest


TOOLS = Path(__file__).resolve().parents[1] / "src/tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("refresh_asrun_priority", TOOLS / "refresh_asrun_priority.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_mart(path, minutes=1440, history=1):
    with duckdb.connect() as con:
        con.execute("CREATE TABLE data(source VARCHAR, log_date VARCHAR, minute_ist VARCHAR, value BIGINT)")
        con.execute("INSERT INTO data VALUES ('fast','2026-10-17','2026-10-17 00:00:00',?)", [history])
        con.execute(
            "INSERT INTO data SELECT source, '2026-10-18', "
            "strftime(TIMESTAMP '2026-10-18' + i * INTERVAL '1 minute','%Y-%m-%d %H:%M:%S'),1 "
            "FROM (VALUES ('fast'),('stream')) s(source), range(?) t(i)", [minutes])
        con.execute("COPY data TO ? (FORMAT PARQUET)", [str(path)])


def test_complete_day_and_history(tmp_path):
    before, after = tmp_path / "before.parquet", tmp_path / "after.parquet"
    make_mart(before, 330)
    make_mart(after)
    assert len(MODULE.validate_identity(before, after, "2026-10-18")) == 2


def test_partial_day_rejected(tmp_path):
    before, after = tmp_path / "before.parquet", tmp_path / "after.parquet"
    make_mart(before, 330)
    make_mart(after, 330)
    with pytest.raises(RuntimeError, match="Incomplete"):
        MODULE.validate_identity(before, after, "2026-10-18")


def test_history_mutation_rejected(tmp_path):
    before, after = tmp_path / "before.parquet", tmp_path / "after.parquet"
    make_mart(before, 330)
    make_mart(after, history=2)
    with pytest.raises(RuntimeError, match="history changed"):
        MODULE.validate_identity(before, after, "2026-10-18")


def test_publish_preserves_previous_files(tmp_path):
    source, destination, backup = (tmp_path / name for name in ("new", "live", "backup"))
    source.mkdir()
    destination.mkdir()
    (source / "index.html").write_text("new")
    (destination / "index.html").write_text("previous")
    MODULE.publish(source, destination, backup)
    assert (destination / "index.html").read_text() == "new"
    assert (backup / "index.html").read_text() == "previous"
