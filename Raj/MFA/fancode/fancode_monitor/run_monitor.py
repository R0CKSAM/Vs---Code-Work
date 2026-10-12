"""
run_monitor.py – Command-line interface for FanCode Monitor & Orchestrator (Phase 10 & 11).

Usage:
  python run_monitor.py --once
  python run_monitor.py --once --dry-run
  python run_monitor.py --interval 300
  python run_monitor.py --health
  python run_monitor.py --diagnostics
  python run_monitor.py --cleanup --dry-run
  python run_monitor.py --cleanup --yes
  python run_monitor.py --once --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.config.validation import ConfigurationValidationError, assert_valid_settings
from app.database.connection import get_session, init_db
from app.maintenance.retention import DataRetentionCleaner
from app.monitor.health import MonitorHealth
from app.monitor.healthcheck import run_healthcheck
from app.monitor.models import ExitCode, PipelineStatus
from app.monitor.runner import MonitorRunner
from app.observability.diagnostics import collect_system_diagnostics, format_diagnostics_text
from app.observability.logging_config import configure_logging

logger = logging.getLogger("run_monitor")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FanCode Monitoring, Observability & Data Maintenance CLI (Phase 11)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute exactly one pipeline cycle and exit immediately",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=getattr(settings, "MONITOR_INTERVAL_SECONDS", 300),
        help="Polling interval in seconds for continuous scheduled execution",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without committing database mutations or dispatching real emails",
    )
    parser.add_argument(
        "--status", "--health",
        dest="show_status",
        action="store_true",
        help="Display current system health, lock state, and recent monitor run summary",
    )
    parser.add_argument(
        "--diagnostics",
        dest="show_diagnostics",
        action="store_true",
        help="Run database integrity check and output operational diagnostics & metrics",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate config, DB, SMTP, Playwright, lock, and heartbeat readiness",
    )
    parser.add_argument(
        "--cleanup",
        dest="do_cleanup",
        action="store_true",
        help="Execute data retention cleanup for expired operational audit records",
    )
    parser.add_argument(
        "--yes", "-y",
        dest="confirm_yes",
        action="store_true",
        help="Confirm destructive retention cleanup without prompt",
    )
    parser.add_argument(
        "--stage",
        type=str,
        default=None,
        help="Execute only a specific pipeline stage (e.g. schedule, live_now, videos, change_detection, notifications)",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        default=True,
        help="Skip broad link discovery crawler (default: True for operational efficiency)",
    )
    parser.add_argument(
        "--include-discovery",
        dest="skip_discovery",
        action="store_false",
        help="Include discovery crawler in the cycle",
    )
    parser.add_argument(
        "--skip-notifications",
        action="store_true",
        default=False,
        help="Skip notification dispatching stage",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=getattr(settings, "MONITOR_MAX_RETRIES", 1),
        help="Maximum retry attempts per failed stage",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in visible (headed) mode for inspection",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as machine-readable JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    configure_logging(
        level=getattr(settings, "LOG_LEVEL", "INFO"),
        structured_json=getattr(settings, "LOG_STRUCTURED", False),
    )

    try:
        assert_valid_settings()
    except ConfigurationValidationError as e:
        logger.error("%s", e)
        print(f"\n[!] Configuration Error: {e}\n", file=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)

    init_db()

    if args.healthcheck:
        report = run_healthcheck()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Healthcheck: {report['status']}")
            for name, check in report["checks"].items():
                print(f"  {name:<12}: {'PASS' if check.get('ok') else 'FAIL'}")
        return int(ExitCode.SUCCESS if report["status"] == "PASS" else ExitCode.PARTIAL)

    # 1. Health / Status query
    if args.show_status:
        status_info = MonitorHealth.get_status()
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(MonitorHealth.format_text(status_info))
        return int(ExitCode.SUCCESS)

    # 2. Operational Diagnostics & DB Integrity
    if args.show_diagnostics:
        diag = collect_system_diagnostics()
        if args.json:
            print(json.dumps(diag, indent=2))
        else:
            print(format_diagnostics_text(diag))
        return int(ExitCode.SUCCESS if diag.get("status") == "HEALTHY" else ExitCode.PARTIAL)

    # 3. Data Retention Cleanup
    if args.do_cleanup:
        if not args.dry_run and not args.confirm_yes:
            print(
                "\n[!] Safety check: Retention cleanup is destructive.\n"
                "    Supply --yes to confirm deletion or use --cleanup --dry-run to simulate.\n",
                file=sys.stderr,
            )
            return int(ExitCode.PARTIAL)

        with get_session() as s:
            report = DataRetentionCleaner.clean(s, dry_run=args.dry_run)

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(DataRetentionCleaner.format_report_text(report))
        return int(ExitCode.SUCCESS)

    # 4. Pipeline Execution
    runner = MonitorRunner()

    try:
        if args.once:
            logger.info("Executing one-shot monitor pipeline run (dry_run=%s)...", args.dry_run)
            result = runner.run_once(
                trigger_type="manual",
                dry_run=args.dry_run,
                skip_discovery=args.skip_discovery,
                skip_notifications=args.skip_notifications,
                stage_filter=args.stage,
                headed=args.headed,
            )

            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"\n===========================================================")
                print(f"   FanCode Monitor Run Summary — Status: {result.status.value}")
                print(f"===========================================================")
                print(f"  Run ID           : #{result.run_id or 'dry-run'}")
                print(f"  Trigger          : {result.trigger_type}")
                print(f"  Duration         : {round(result.duration_seconds, 2)}s")
                print(f"  Dry-Run          : {result.is_dry_run}")
                print("-----------------------------------------------------------")
                print("  Stages Execution:")
                for name, s_res in result.stages.items():
                    status_symbol = "✓" if s_res.status.value == "SUCCESS" else ("-" if s_res.status.value == "SKIPPED" else "✗")
                    print(
                        f"    [{status_symbol}] {name:<18} : {s_res.status.value:<8} "
                        f"({round(s_res.duration_seconds, 2)}s, "
                        f"processed: {s_res.records_processed}, "
                        f"changes: {s_res.changes_detected}, "
                        f"alerts: {s_res.notifications_sent})"
                    )
                if result.error_summary:
                    print(f"  Error Summary    : {result.error_summary}")
                print("===========================================================\n")

            return int(result.exit_code)

        else:
            # Recurring scheduled loop
            logger.info("Starting continuous monitor with interval %ds...", args.interval)
            runner.run_loop(
                interval_seconds=args.interval,
                dry_run=args.dry_run,
                skip_discovery=args.skip_discovery,
                skip_notifications=args.skip_notifications,
                stage_filter=args.stage,
                headed=args.headed,
            )
            return int(ExitCode.SUCCESS)

    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user.")
        return int(ExitCode.INTERRUPTED)


if __name__ == "__main__":
    sys.exit(main())
