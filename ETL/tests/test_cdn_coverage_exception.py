import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/tools"))
from cleanup_daily_intermediates import load_validation_report


def test_scoped_coverage_exception(tmp_path):
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps(dict(kind="operator_confirmed_cdn_loss", reason="confirmed loss",
        confirmed_at="2026-10-23", dates=["2026-10-20"], sources=["fast", "stream"])))
    report = dict(date="2026-10-20", mode="structural", overall_status="FAIL", hard_failure_count=2,
        source_results=[dict(source=s, status="PARTIAL", selected=dict(rows=10, files=["part"], full_day=False))
                        for s in ("fast", "stream")])
    path = tmp_path / "report.json"
    def check():
        path.write_text(json.dumps(report))
        return load_validation_report(path, "2026-10-20", ["fast", "stream"],
                                      allow_lake_only=True, coverage_exception=approval)
    assert check()["overall_status"] == "FAIL"
    with pytest.raises(SystemExit):
        load_validation_report(path, "2026-10-20", ["fast", "stream"], allow_lake_only=True)
    for bad in ("FAILED", "MISSING", "DUPLICATE"):
        report["source_results"][0]["status"] = bad
        with pytest.raises(SystemExit):
            check()
    report["source_results"][0]["status"] = "PARTIAL"
    report["hard_failure_count"] = 3
    with pytest.raises(SystemExit):
        check()
    report["hard_failure_count"] = 2
    report["date"] = "2026-10-21"
    with pytest.raises(SystemExit):
        check()
