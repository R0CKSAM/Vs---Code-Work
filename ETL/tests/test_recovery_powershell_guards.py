from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path


ETL_ROOT = Path(__file__).resolve().parents[1]
DAILY_SCRIPT = ETL_ROOT / "run_daily_pipeline.ps1"
RECOVERY_SCRIPT = ETL_ROOT / "run_recovery_pipeline.ps1"
INSTALL_SCRIPT = ETL_ROOT / "install_recovery_task.ps1"
PREFETCH_SCRIPT = ETL_ROOT / "prefetch_daily_sources.ps1"
WORKER_SCRIPT = ETL_ROOT / "sync_daily_source.ps1"
TEST_TEMP_ROOT = Path(tempfile.gettempdir()) / "veto_etl_tests"


class RecoveryPowerShellGuardsTest(unittest.TestCase):
    def test_fresh_validation_timestamp_does_not_dereference_nullable_value(self) -> None:
        source = RECOVERY_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("$NotBefore.Value.ToUniversalTime()", source)
        self.assertIn("([datetime]$NotBefore).ToUniversalTime()", source)

    def test_scripts_parse_without_errors(self) -> None:
        escaped_paths = [
            str(path).replace("'", "''")
            for path in (
                DAILY_SCRIPT,
                RECOVERY_SCRIPT,
                INSTALL_SCRIPT,
                PREFETCH_SCRIPT,
                WORKER_SCRIPT,
            )
        ]
        paths = ",".join(f"'{path}'" for path in escaped_paths)
        command = (
            f"$failed=$false; foreach($path in @({paths})) {{ "
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null; "
            "if($errors.Count) { $failed=$true; $errors | ForEach-Object { Write-Error $_.Message } } }; "
            "if($failed) { exit 1 }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_six_slot_prefetch_validates_all_source_date_jobs(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temp:
            root = Path(temp)
            fake_rclone = root / "fake_rclone.ps1"
            raw_root = root / "raw"
            log_root = root / "logs"
            result_root = root / "results"
            fake_rclone.write_text(
                """
param(
    [Parameter(Position = 0)][string]$Operation,
    [Parameter(Position = 1)][string]$SourcePath,
    [Parameter(Position = 2)][string]$DestinationPath,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining
)
if ($Operation -eq 'size') {
    if ($SourcePath -match '^[^\\/:]+:.+') {
        '{\"count\":1,\"bytes\":2}'
    } else {
        $files = @(Get-ChildItem -LiteralPath $SourcePath -File -Recurse -ErrorAction SilentlyContinue)
        $bytes = ($files | Measure-Object -Property Length -Sum).Sum
        if ($null -eq $bytes) { $bytes = 0 }
        @{ count = $files.Count; bytes = [int64]$bytes } | ConvertTo-Json -Compress
    }
    exit 0
}
if ($Operation -eq 'sync') {
    New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $DestinationPath 'sample.gz'), [byte[]](111, 107))
    Start-Sleep -Milliseconds 150
    exit 0
}
exit 3
""".strip(),
                encoding="utf-8",
            )

            def quote(path: Path) -> str:
                return str(path).replace("'", "''")

            command = (
                f"& '{quote(PREFETCH_SCRIPT)}' "
                "-Dates @([datetime]'2026-08-13',[datetime]'2026-08-14',[datetime]'2026-08-15') "
                f"-RawRoot '{quote(raw_root)}' "
                f"-RcloneExe '{quote(fake_rclone)}' "
                f"-DownloadLogRoot '{quote(log_root)}' "
                f"-DownloadResultRoot '{quote(result_root)}' "
                "-MaxParallelDownloads 6 -Transfers 16 -Checkers 32"
            )
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
            )

            results = sorted(result_root.glob("*.json"))
            self.assertEqual(len(results), 6)
            for result_path in results:
                result = json.loads(result_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(result["status"], "complete")
                self.assertTrue(result["verified"])
                self.assertEqual(result["transfers"], 16)
                self.assertEqual(result["checkers"], 32)

    def test_old_array_splat_invocation_is_rejected_before_io(self) -> None:
        script = str(DAILY_SCRIPT).replace("'", "''")
        command = (
            "$values=@('-Date','2026-08-14','-SkipPostVerifyDelay','-SkipWatch',"
            "'-SkipOverview','-SkipLakeArchive'); "
            f"try {{ & '{script}' @values; exit 2 }} catch {{ "
            "if($_.Exception.Message -match 'Unexpected positional arguments|Invalid rclone remote root') { exit 0 }; "
            "Write-Error $_.Exception.Message; exit 1 }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
