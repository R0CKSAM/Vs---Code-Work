from __future__ import annotations

import json
import sys
from pathlib import Path

from dashboard_automation.config import DashboardAutomationConfig
from dashboard_automation.logging_utils import configure_logging
from dashboard_automation.pipeline import process_new_files
from landing_channel_tracker import process_landing_tracker_files


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    config = DashboardAutomationConfig(base_dir=base_dir)
    logger = configure_logging(config)

    print("\n--- Running Landing Channel Change Tracker Update Pipeline ---")
    try:
        # 1. Process Landing Channel Excel files inside landing/
        landing_summary = process_landing_tracker_files()
        print(f"Landing Update Summary: {json.dumps(landing_summary)}")
    except Exception as error:
        print(f"Landing processing warning: {error}", file=sys.stderr)

    print("\n--- Refreshing Dashboard Data & HTML ---")
    try:
        # 2. Run automation pipeline & regenerate dashboard HTML
        result = process_new_files(config, logger=logger)
        print("\nDashboard update completed successfully!")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:  # noqa: BLE001
        logger.exception("Dashboard update failed: %s", error)
        print(f"Dashboard update failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
