from __future__ import annotations

import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "processed"
DASHBOARD_DIR = ROOT / "dashboard"
TEMPLATE_PATH = DASHBOARD_DIR / "template.html"
OUTPUT_PATH = DASHBOARD_DIR / "dashboard_output.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("build_dashboard")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required data file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main() -> int:
    distribution_master = load_json(PROCESSED_DIR / "distribution_master.json")
    channel_weekly = load_json(PROCESSED_DIR / "channel_weekly.json")
    processed_log = load_json(PROCESSED_DIR / "_processed_log.json")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = (
        template.replace("__DISTRIBUTION_MASTER_JSON__", json.dumps(distribution_master, ensure_ascii=False))
        .replace("__CHANNEL_WEEKLY_JSON__", json.dumps(channel_weekly, ensure_ascii=False))
        .replace("__PROCESSED_LOG_JSON__", json.dumps(processed_log, ensure_ascii=False))
    )

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    LOGGER.info("Generated standalone dashboard: %s", OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
