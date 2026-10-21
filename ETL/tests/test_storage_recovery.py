import gzip
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative):
    spec = importlib.util.spec_from_file_location("storage_test_module", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fail_at", ["open", "write"])
def test_output_failure_stops_before_next_input(tmp_path, monkeypatch, fail_at):
    converter = load_module("src/pipeline/001.py")
    first = tmp_path / "first.gz"
    with gzip.open(first, "wb") as handle:
        handle.write(b'{"value":1}\n')
    opened = []
    real_open = converter.gzip.open

    def tracked_open(path, *args, **kwargs):
        opened.append(path)
        return real_open(path, *args, **kwargs)

    class FailingWriter:
        def __init__(self, *args, **kwargs):
            if fail_at == "open":
                raise OSError(28, "No space left on device")

        def write_table(self, *args, **kwargs):
            raise OSError(28, "No space left on device")

        def close(self):
            pass

    monkeypatch.setattr(converter.gzip, "open", tracked_open)
    monkeypatch.setattr(converter.pq, "ParquetWriter", FailingWriter)
    output = tmp_path / "part.parquet"
    result = converter._convert_batch(dict(
        out_path=str(output), files=[str(first), str(tmp_path / "next.gz")],
        compression="snappy", row_buffer=1, row_group_size=1, add_meta=False,
        placeholders=[], cols_to_keep=[], cols_to_drop=[],
    ))
    assert result["status"] == "error"
    assert "No space left" in result["error"]
    assert result["failed_files"] == []
    assert opened == [str(first)]
    assert not output.exists()


def test_configured_final_clean_path(tmp_path, monkeypatch):
    pipeline = load_module("src/orchestrator/run_pipeline.py")
    monkeypatch.delenv("VG_ETL_FINAL_CLEAN_ROOT", raising=False)
    base = tmp_path / "data"
    default = pipeline._final_clean_file(base, "stream", date(2026, 10, 20))
    assert default.is_relative_to(base / "stage" / "final_clean")
    external = tmp_path / "nas" / "final_clean"
    monkeypatch.setenv("VG_ETL_FINAL_CLEAN_ROOT", str(external))
    path = pipeline._final_clean_file(base, "stream", date(2026, 10, 20))
    assert path.is_relative_to(external)
    assert path.name == "stream_2026_10_20_final_clean.parquet"


def test_only_reconciled_review_can_defer_cleanup(tmp_path):
    pipeline = load_module("src/orchestrator/run_pipeline.py")
    report_path = tmp_path / "report.json"
    report = dict(
        mode="full", date="2026-10-20", overall_status="REVIEW", hard_failure_count=0,
        source_results=[dict(source="stream", status="PASS", selected=dict(full_day=True))],
        profile_reconciliation=[dict(source="stream", status="PASS", delta_rows=0)],
    )
    def check():
        report_path.write_text(json.dumps(report))
        return pipeline._cleanup_has_review_only(report_path, "2026-10-20", ["stream"])
    assert check()
    for field, value in [("hard_failure_count", 1), ("mode", "structural"), ("date", "2026-10-19")]:
        old = report[field]
        report[field] = value
        assert not check()
        report[field] = old
    report["profile_reconciliation"][0]["delta_rows"] = 1
    assert not check()
    report["profile_reconciliation"][0]["delta_rows"] = 0
    report["source_results"][0]["selected"]["full_day"] = False
    assert not check()


@pytest.mark.parametrize("status", ["PASS", "REVIEW"])
def test_external_final_cleanup_requires_validation(tmp_path, status):
    base = tmp_path / "data"
    lake = base / "lake"
    external = tmp_path / "nas" / "final_clean"
    suffix = Path("source=stream/year=2026/month=10/day=20")
    final = external / suffix / "stream_2026_10_20_final_clean.parquet"
    retained = lake / suffix / "part_stream_2026_10_20_0.parquet"
    unrelated = external / "keep.txt"
    for path in (final, retained):
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"value": [1, 2]}), path)
    unrelated.write_text("retain")
    report = tmp_path / "validation.json"
    report.write_text(json.dumps(dict(
        mode="full", date="2026-10-20", overall_status=status, hard_failure_count=0,
        source_results=[dict(source="stream", status="PASS", selected=dict(full_day=True))],
        profile_reconciliation=[dict(source="stream", status="PASS", row_delta=0)],
    )))
    completed = subprocess.run([
        sys.executable, str(ROOT / "src/tools/cleanup_daily_intermediates.py"),
        "--base", str(base), "--lake", str(lake), "--final-clean-root", str(external),
        "--raw-root", str(base / "raw"), "--date", "2026-10-20", "--sources", "stream",
        "--validation-report", str(report), "--audit-dir", str(tmp_path / "audit"), "--execute",
    ], capture_output=True, text=True)
    assert (completed.returncode == 0) == (status == "PASS"), completed.stderr
    assert final.exists() == (status != "PASS")
    assert retained.exists() and unrelated.exists() and external.exists()
