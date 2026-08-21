from __future__ import annotations

from pathlib import Path


ETL_ROOT = Path(__file__).resolve().parents[1]


def test_overview_is_rendered_once_after_downstream_marts() -> None:
    source = (ETL_ROOT / "src" / "orchestrator" / "run_pipeline.py").read_text(encoding="utf-8")
    assert 'step_name="overview_report_xlsx"' not in source
    assert source.count('step_name="overview_report_xlsx_after_latency_identity"') == 1
    assert source.count('step_name="overview_dashboard_html_after_identity"') == 1
    assert "overview refresh will run once after latency and identity marts" in source


def test_daily_dedupe_uses_eight_memory_safe_buckets() -> None:
    source = (ETL_ROOT / "src" / "pipeline" / "02.py").read_text(encoding="utf-8")
    assert 'VG_ETL_DEDUPE_BUCKETS", "8"' in source
    assert 'SELECT DISTINCT *' in source


def test_daily_stage_uses_fast_temporary_compression() -> None:
    source = (ETL_ROOT / "run_daily_pipeline.ps1").read_text(encoding="utf-8")
    assert '[string]$StageCompression = "snappy"' in source
    assert '$("--stage-compression", $StageCompression)' not in source
    assert '@("--stage-compression", $StageCompression)' in source


def test_skipping_watch_html_does_not_skip_concurrency_data() -> None:
    source = (ETL_ROOT / "src" / "orchestrator" / "run_pipeline.py").read_text(encoding="utf-8")
    assert "if not args.skip_concurrency:" in source
    assert "if not args.skip_watch and not args.skip_concurrency:" not in source


def test_daily_run_caps_dashboard_publication_at_validated_target() -> None:
    source = (ETL_ROOT / "run_daily_pipeline.ps1").read_text(encoding="utf-8")
    assert '"--publish-through", $TargetDate.ToString("yyyy-MM-dd")' in source


def test_daily_archives_completed_target_and_keeps_only_spillover_hot() -> None:
    source = (ETL_ROOT / "run_daily_pipeline.ps1").read_text(encoding="utf-8")
    assert "[ValidateRange(1, 31)]" in source
    assert "[int]$HotLakeRetentionDays = 1" in source
    assert "$ArchiveThrough = $TargetDate.Date.AddDays(1 - $HotLakeRetentionDays)" in source
    assert "archiving completed partitions through" in source
