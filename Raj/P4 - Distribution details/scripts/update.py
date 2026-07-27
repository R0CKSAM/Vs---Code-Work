from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from parser import parse_workbook

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "processed"
DISTRIBUTION_PATH = PROCESSED_DIR / "distribution_master.json"
CHANNEL_WEEKLY_PATH = PROCESSED_DIR / "channel_weekly.json"
PROCESSED_LOG_PATH = PROCESSED_DIR / "_processed_log.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("update")


def ensure_directories() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def list_unprocessed_files(processed_log: dict[str, Any]) -> list[Path]:
    processed_names = {entry["filename"] for entry in processed_log.get("processed_files", [])}
    return [
        path
        for path in sorted(RAW_DIR.glob("*.xlsx"))
        if not path.name.startswith("~$") and path.name not in processed_names
    ]


def upsert_distribution(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_headend = {row["headend_id"]: row for row in existing_rows}

    for row in new_rows:
        current = by_headend.get(row["headend_id"])
        if current is None:
            by_headend[row["headend_id"]] = row
            continue

        current_date = current.get("date") or ""
        new_date = row.get("date") or ""
        if new_date >= current_date:
            merged = current.copy()
            merged.update(row)
            by_headend[row["headend_id"]] = merged

    return sorted(by_headend.values(), key=lambda item: (item.get("state") or "", item.get("headend_location") or "", item["headend_id"]))


def merge_channel_weekly(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for row in existing_rows:
        key = (row["headend_id"], str(row["lcn_no"]))
        by_key[key] = row

    for row in new_rows:
        week = row.get("date") or "NA"

        key = (row["headend_id"], str(row["lcn_no"]))
        entry = by_key.get(
            key,
            {
                "headend_id": row["headend_id"],
                "lcn_no": str(row["lcn_no"]),
            },
        )
        entry[week] = row["channel_name"]
        by_key[key] = entry

    def sort_key(item: dict[str, Any]) -> tuple[str, int | str]:
        lcn_value = str(item.get("lcn_no") or "")
        if lcn_value.isdigit():
            return (item.get("headend_id") or "", 0, int(lcn_value))
        return (item.get("headend_id") or "", 1, lcn_value)

    return sorted(by_key.values(), key=sort_key)


def update_processed_log(
    processed_log: dict[str, Any],
    file_path: Path,
    week_dates: list[str],
    headend_count: int,
    channel_count: int,
) -> dict[str, Any]:
    processed_files = processed_log.setdefault("processed_files", [])
    processed_files.append(
        {
            "filename": file_path.name,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "weeks_found": week_dates,
            "headend_snapshots": headend_count,
            "channel_rows": channel_count,
        }
    )
    return processed_log


def merge_normalization_warnings(
    aggregate: dict[str, Counter[str]],
    current: dict[str, dict[str, int]],
) -> None:
    for field, values in current.items():
        aggregate.setdefault(field, Counter()).update(values)


def log_normalization_warnings(aggregate: dict[str, Counter[str]]) -> None:
    active_fields = {field: counter for field, counter in aggregate.items() if counter}
    if not active_fields:
        return

    LOGGER.warning("Unrecognized values this run - add to normalization map if valid:")
    for field in ("state", "headend_location", "barc_market"):
        counter = active_fields.get(field)
        if not counter:
            continue
        LOGGER.warning("  %s:", field)
        for raw_value, count in counter.most_common():
            LOGGER.warning("    %s (%s rows)", raw_value, count)


def main() -> int:
    ensure_directories()
    distribution_master = load_json(DISTRIBUTION_PATH, [])
    channel_weekly = load_json(CHANNEL_WEEKLY_PATH, [])
    processed_log = load_json(PROCESSED_LOG_PATH, {"processed_files": []})

    normalization_warnings: dict[str, Counter[str]] = {
        "state": Counter(),
        "headend_location": Counter(),
        "barc_market": Counter(),
    }

    pending_files = list_unprocessed_files(processed_log)
    if not pending_files:
        LOGGER.info("No new Excel files found in %s.", RAW_DIR)
        return 0

    for workbook_path in pending_files:
        LOGGER.info("Processing workbook: %s", workbook_path.name)
        parsed = parse_workbook(workbook_path)
        distribution_master = upsert_distribution(distribution_master, parsed.distribution_rows)
        channel_weekly = merge_channel_weekly(channel_weekly, parsed.channel_rows)
        merge_normalization_warnings(normalization_warnings, parsed.normalization_warnings)
        processed_log = update_processed_log(
            processed_log=processed_log,
            file_path=workbook_path,
            week_dates=parsed.week_dates,
            headend_count=len(parsed.distribution_rows),
            channel_count=len(parsed.channel_rows),
        )

    write_json(DISTRIBUTION_PATH, distribution_master)
    write_json(CHANNEL_WEEKLY_PATH, channel_weekly)
    write_json(PROCESSED_LOG_PATH, processed_log)

    all_weeks = sorted(
        {
            key
            for row in channel_weekly
            for key in row.keys()
            if key not in {"headend_id", "lcn_no"}
        }
    )

    LOGGER.info("Updated %s", DISTRIBUTION_PATH)
    LOGGER.info("Updated %s", CHANNEL_WEEKLY_PATH)
    LOGGER.info("Updated %s", PROCESSED_LOG_PATH)
    LOGGER.info("Total headends: %s", len(distribution_master))
    LOGGER.info("Total channel rows: %s", len(channel_weekly))
    LOGGER.info("Available week columns: %s", len(all_weeks))
    log_normalization_warnings(normalization_warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
