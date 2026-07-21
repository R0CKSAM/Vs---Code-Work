from __future__ import annotations

import json
import sys
from pathlib import Path

from dashboard_automation.config import DashboardAutomationConfig
from dashboard_automation.logging_utils import configure_logging
from dashboard_automation.pipeline import process_new_files


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    config = DashboardAutomationConfig(base_dir=base_dir)
    logger = configure_logging(config)

    try:
        result = process_new_files(config, logger=logger)
    except Exception as error:  # noqa: BLE001
        logger.exception("Dashboard update failed: %s", error)
        print("Dashboard update failed. Check logs/dashboard_automation.log for details.", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
