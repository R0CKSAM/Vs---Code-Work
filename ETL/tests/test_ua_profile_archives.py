import argparse
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
import build_ua_profile_incremental as ua

DAY = date(2026, 10, 18)


def write_part(root, name, n=1, source="stream"):
    folder = ua.day_path(root, source, DAY)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    pd.DataFrame([dict(reqTimeSec=datetime(2026, 10, 18, 8, tzinfo=timezone.utc).timestamp(),
                       UA="Test TV", cliIP="192.0.2.1", reqHost="example.test", reqPath="/a.ts", statusCode=200)] * n).to_parquet(path)
    return path


def args_for(tmp_path, files):
    return argparse.Namespace(lake=tmp_path / "hot", day_files=files, parts_dir=tmp_path / "parts",
                              out_dir=tmp_path / "out", source="stream", force=False, dry_run=False,
                              threads=1, memory_limit="256MB", temp_dir=tmp_path / "scratch")


def test_archive_only_and_incremental_skip(tmp_path):
    archive = tmp_path / "archive"
    write_part(archive, "part_01.parquet", 3)
    files = ua.discover_day_files(tmp_path / "hot", ["stream"], DAY, DAY, [archive])
    args = args_for(tmp_path, files)
    assert ua.process_day(args, "stream", DAY)["raw_rows"] == 3
    assert ua.process_day(args, "stream", DAY)["status"] == "skipped"
    merged, _ = ua.merge_parts(args, list(files))
    assert merged["rows"].sum() == 3


def test_split_day_and_duplicate_copy_counted_once(tmp_path):
    hot, archive = tmp_path / "hot", tmp_path / "archive"
    write_part(hot, "part_01.parquet", 2)
    write_part(archive, "part_01.parquet", 2)
    write_part(archive, "part_02.parquet", 3)
    write_part(archive, "tmp_pending.parquet", 20)
    files = ua.discover_day_files(hot, ["stream"], DAY, DAY, [archive])
    assert len(files[("stream", DAY)]) == 2
    with duckdb.connect() as con:
        frame = con.execute(ua.day_sql(args_for(tmp_path, files), "stream", DAY)).fetchdf()
    assert frame["rows"].sum() == 5


def test_archive_environment_and_date_filter(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    write_part(archive, "part_01.parquet", source="fast")
    monkeypatch.setattr(ua, "resolve_lake_roots", lambda primary, archives: [primary, archive])
    assert ua.discover_days(tmp_path / "hot", ["fast"], DAY, DAY) == [("fast", DAY)]
    assert not ua.discover_days(tmp_path / "hot", ["stream"], DAY, DAY)
    assert not ua.discover_days(tmp_path / "hot", ["fast"], date(2026, 10, 19), date(2026, 10, 19))


def test_signature_changes_when_archive_file_added(tmp_path):
    archive = tmp_path / "archive"
    first = write_part(archive, "part_01.parquet")
    before = ua.signature_for_day(tmp_path / "hot", "stream", DAY, [first])
    second = write_part(archive, "part_02.parquet")
    after = ua.signature_for_day(tmp_path / "hot", "stream", DAY, [first, second])
    assert before != after
    assert after["file_count"] == 2
