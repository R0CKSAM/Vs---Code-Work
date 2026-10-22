from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/tools"))
import cleanup_daily_intermediates as cleanup
import run_core_lake_priority as core
import prepared_priority_lake as prepared


def test_historical_repair_dependency(tmp_path):
    path = tmp_path / "repair.json"
    path.write_text(json.dumps({"status": "running"}))
    def finish(_):
        path.write_text(json.dumps({"status": "core_repair_complete_external_asrun_pending"}))
    with patch.object(core.time, "sleep", side_effect=finish) as sleep:
        core.wait_for_repair(path)
        sleep.assert_called_once()
    path.write_text(json.dumps({"status": "failed"}))
    with pytest.raises(RuntimeError, match="Historical repair failed"):
        core.wait_for_repair(path)
    path.write_text(json.dumps({"status": "running"}))
    with pytest.raises(RuntimeError, match="timeout"):
        core.wait_for_repair(path, timeout=0)


def report_file(tmp_path, mode="structural", status="PASS", full=True, failures=0):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(dict(date="2026-10-21", mode=mode, overall_status=status,
        hard_failure_count=failures, source_results=[dict(source="stream", status="PASS",
        selected=dict(full_day=full))])))
    return path


def test_structural_retirement_requires_explicit_opt_in(tmp_path):
    report = report_file(tmp_path)
    with pytest.raises(SystemExit):
        cleanup.load_validation_report(report, "2026-10-21", ["stream"])
    assert cleanup.load_validation_report(report, "2026-10-21", ["stream"], allow_lake_only=True)["mode"] == "structural"


@pytest.mark.parametrize("changes", [dict(status="FAIL"), dict(full=False), dict(failures=1), dict(mode="unknown")])
def test_partial_or_failed_lake_cannot_retire_inputs(tmp_path, changes):
    with pytest.raises(SystemExit):
        cleanup.load_validation_report(report_file(tmp_path, **changes), "2026-10-21", ["stream"], allow_lake_only=True)


def test_new_mode_does_not_bypass_full_profile_mismatch(tmp_path):
    with pytest.raises(SystemExit):
        cleanup.load_validation_report(report_file(tmp_path, mode="full"), "2026-10-21", ["stream"], allow_lake_only=True)


def test_download_must_be_fresh_verified_and_exact(tmp_path):
    path = tmp_path / "download.json"
    before = datetime(2026, 10, 22, tzinfo=timezone.utc)
    data = dict(status="complete", verified=True, date="2026-10-21", source="stream",
        local_count=2, remote_count=2, local_bytes=10, remote_bytes=10, finished_at_ist=before.isoformat())
    path.write_text(json.dumps(data))
    core.verified_download(path, "2026-10-21", "stream", before)
    for key, value in [("verified", False), ("local_bytes", 9), ("local_count", 1),
                       ("finished_at_ist", "2026-10-21T00:00:00+00:00")]:
        path.write_text(json.dumps({**data, key: value}))
        with pytest.raises(RuntimeError):
            core.verified_download(path, "2026-10-21", "stream", before)


def test_priority_wait_never_interrupts_current_pipeline(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    request = state / "core_lake_priority.json"
    request.write_text(json.dumps(dict(status="waiting", pid=100, state_names=["core"])))
    with patch("run_pipeline._process_is_running", return_value=True):
        core_module = sys.modules["run_pipeline"]
        core_module.wait_for_core_priority(tmp_path, "core", timeout=0)
        with pytest.raises(RuntimeError, match="Timed out"):
            core_module.wait_for_core_priority(tmp_path, "repair", timeout=0)
        (state / "pipeline.lock").write_text('{"pid":200}')
        with pytest.raises(RuntimeError, match="Timed out"):
            core_module.wait_for_core_priority(tmp_path, "core", timeout=0)


def test_core_receipt_reuses_lake_without_raw_or_final(tmp_path, monkeypatch):
    monkeypatch.setattr(prepared, "ETL", tmp_path)
    base = tmp_path / "data"
    sources = {}
    for source in ("fast", "stream"):
        checkpoint = tmp_path / "output/state/downloads" / f"2026-10-21_{source}.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text('{}')
        lake = base / "lake" / source / "part.parquet"
        lake.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"x": [1, 2]}), lake)
        sources[source] = dict(rows=2, download_checkpoint_sha256=prepared.sha256(checkpoint),
                               lake=[prepared.fingerprint(lake)])
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(dict(status="lake_ready", date="2026-10-21", sources=sources)))
    assert prepared.verify(receipt, base)["status"] == "lake_ready"
    sources["fast"]["rows"] = 3
    receipt.write_text(json.dumps(dict(status="lake_ready", date="2026-10-21", sources=sources)))
    with pytest.raises(RuntimeError, match="row count mismatch"):
        prepared.verify(receipt, base)
