from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb


ETL_ROOT = Path(__file__).resolve().parents[1]


def load_stage_module():
    path = ETL_ROOT / "src" / "pipeline" / "02.py"
    spec = importlib.util.spec_from_file_location("etl_stage_02", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eight_bucket_dedupe_matches_legacy_thirty_two_buckets(tmp_path: Path) -> None:
    stage = load_stage_module()
    stage.TEMP_DIR = tmp_path / "scratch"
    stage.COMPRESSION_CHAIN = ["SNAPPY"]

    con = duckdb.connect()
    source = tmp_path / "input.parquet"
    out_eight = tmp_path / "eight.parquet"
    out_thirty_two = tmp_path / "thirty_two.parquet"
    con.execute(
        f"""
        COPY (
            SELECT
                CASE WHEN value % 11 = 0 THEN NULL ELSE value % 37 END::INTEGER AS id,
                CASE WHEN value % 7 = 0 THEN NULL ELSE 'channel_' || (value % 9) END AS channel,
                CASE WHEN value % 5 = 0 THEN '-' ELSE CAST(value % 13 AS VARCHAR) END AS marker
            FROM range(0, 2000) AS rows(value)
            UNION ALL
            SELECT 1, 'channel_1', '1' FROM range(0, 50)
        ) TO '{source.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY)
        """
    )

    input_rows = stage.parquet_row_count(con, source.as_posix())
    stage.dedupe_bucketed(con, source.as_posix(), out_eight, 8)
    stage.dedupe_bucketed(con, source.as_posix(), out_thirty_two, 32)

    eight_rows = stage.parquet_row_count(con, out_eight.as_posix())
    legacy_rows = stage.parquet_row_count(con, out_thirty_two.as_posix())
    assert eight_rows < input_rows
    assert eight_rows == legacy_rows

    missing_from_eight = con.execute(
        f"SELECT COUNT(*) FROM (SELECT * FROM read_parquet('{out_thirty_two.as_posix()}') EXCEPT SELECT * FROM read_parquet('{out_eight.as_posix()}'))"
    ).fetchone()[0]
    missing_from_legacy = con.execute(
        f"SELECT COUNT(*) FROM (SELECT * FROM read_parquet('{out_eight.as_posix()}') EXCEPT SELECT * FROM read_parquet('{out_thirty_two.as_posix()}'))"
    ).fetchone()[0]
    assert missing_from_eight == 0
    assert missing_from_legacy == 0
    con.close()
