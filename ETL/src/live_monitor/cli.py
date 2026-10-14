from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
from dataclasses import replace

from .config import LiveConfig
from .engine import InstanceLock, LiveEngine, atomic_write_json
from .store import LiveStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable near-live CDN monitor")
    parser.add_argument("command", nargs="?", choices=("run", "doctor", "status", "retain"), default="run")
    parser.add_argument("--budget-seconds", type=float, default=60,
                        help="Maximum deletion work per offline retention pass")
    parser.add_argument("--no-sync", action="store_true", help="Process existing local files only")
    parser.add_argument("--workers", type=int, help="Bounded parser worker count")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LiveConfig()
    if args.workers:
        config = replace(config, parse_workers=max(1, min(12, args.workers)))
    config.state_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
        handlers=[TimedRotatingFileHandler(config.log_path, when="midnight",
                  backupCount=config.retention_days, encoding="utf-8"), logging.StreamHandler()],
    )
    if args.command == "doctor":
        checks = {
            "rclone": str(config.rclone_exe),
            "rclone_exists": config.rclone_exe.is_file(),
            "spool": str(config.spool_root),
            "spool_exists": config.spool_root.is_dir(),
            "database": str(config.database_path),
            "snapshot": str(config.snapshot_path),
            "watched_paths": list(config.watched_paths),
            "dashboard": f"http://{config.http_host}:{config.http_port}",
            "retention_previous_days": config.retention_days,
        }
        print(json.dumps(checks, indent=2))
        return int(
            (args.no_sync and not checks["spool_exists"])
            or (not args.no_sync and not checks["rclone_exists"])
        )
    if args.command == "retain":
        with InstanceLock(config.state_dir / "live_monitor.lock"):
            if not config.database_path.is_file():
                raise RuntimeError("No live-monitor database exists; nothing to retain")
            result = LiveStore(config.database_path).prune_history(
                config.retention_days, budget_seconds=args.budget_seconds
            )
            atomic_write_json(config.state_dir / "retention_status.json", result)
            print(json.dumps(result, indent=2))
            return 0 if result["complete"] else 2
    engine = LiveEngine(config, sync_enabled=not args.no_sync)
    if args.command == "status":
        print(json.dumps(engine.publish_snapshot(), indent=2))
        return 0
    engine.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
