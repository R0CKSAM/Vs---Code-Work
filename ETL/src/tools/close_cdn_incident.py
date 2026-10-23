"""Close confirmed 20/21 October CDN-loss days without publishing them as complete."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

from check_raw_delivery import atomic_json
from cleanup_daily_intermediates import load_validation_report
from run_core_lake_priority import PipelineRunLock, _process_is_running

ETL = Path(__file__).resolve().parents[2]
WORK = ETL / "output/temp/cdn_incident_20261020_21"
ARCHIVE = Path(r"Z:\Veto Logs Backup\DO NOT DELETE")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    state = dict(status="waiting_for_active_core", completed_dates=[], full_day_complete=False)
    def save():
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(WORK / "state.json", state)
    def run(label, args, accepted_codes=(0,)):
        print(label, flush=True)
        with (WORK / (label + ".log")).open("a", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, "-u", *map(str, args)], cwd=ETL,
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode not in accepted_codes:
            raise RuntimeError(f"{label} failed: exit {result.returncode}")
    save()
    lock = PipelineRunLock(ETL / "output")
    try:
        deadline = time.monotonic() + 7 * 86400
        while True:
            request = json.loads((ETL / "output/state/core_lake_priority.json").read_text())
            if not _process_is_running(int(request.get("pid", 0))):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Timed out waiting for active core worker")
            time.sleep(15)
        lock.acquire()
        approval = ETL / "output/state/cdn_incident_20261020_21.json"
        for day in ("2026-10-20", "2026-10-21"):
            state.update(status="validating", current_date=day)
            save()
            validation = WORK / day / "validation"
            run(day + "_validate", [ETL / "src/tools/validate_daily_delivery.py",
                "--lake", ETL / "data/lake", "--archive-lake", ARCHIVE,
                "--date", day, "--mode", "structural", "--output-dir", validation], (0, 2))
            report = validation / "daily_delivery_validation_latest.json"
            load_validation_report(report, day, ["fast", "stream"], allow_lake_only=True,
                                   coverage_exception=approval)
            # The normal cleanup independently requires exact positive batch/lake row equality.
            final_root = ETL / "data/stage/final_clean" if day.endswith("20") else ARCHIVE / "Temp/VetoETL/final_clean"
            state["status"] = "reconciling_and_cleaning"
            save()
            audit = WORK / day / "cleanup"
            run(day + "_cleanup", [ETL / "src/tools/cleanup_daily_intermediates.py",
                "--base", ETL / "data", "--lake", ETL / "data/lake", "--archive-lake", ARCHIVE,
                "--raw-root", ETL / "data/raw/Veto Logs Backup", "--date", day,
                "--final-clean-root", final_root, "--etl3-state", ETL / "data/.etl_03_state.json",
                "--validation-report", report, "--allow-lake-only-validation",
                "--coverage-exception", approval, "--audit-dir", audit, "--execute"])
            manifests = sorted(audit.glob(f"cleanup_{day}_*.json"))
            if not manifests or json.loads(manifests[-1].read_text())["status"] != "complete":
                raise RuntimeError("Cleanup did not confirm completion")
            receipt = dict(date=day, status="processed_with_confirmed_source_gap",
                           full_day_complete=False, dashboard_eligible=False,
                           approval=str(approval), validation_report=str(report),
                           cleanup_manifest=str(manifests[-1]))
            atomic_json(ETL / "output/state/cdn_incident_closeout" / (day + ".json"), receipt)
            state["completed_dates"].append(day)
            save()
        state["status"] = "available_lake_and_cleanup_complete"
    except BaseException as exc:
        state.update(status="failed", error=str(exc))
        from etl_notifications import notify_failure
        notify_failure("CDN incident closeout", str(exc), state_path=WORK / "state.json")
        raise
    finally:
        lock.release()
        save()


if __name__ == "__main__":
    main()
