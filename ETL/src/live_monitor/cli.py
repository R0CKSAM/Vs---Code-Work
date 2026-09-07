from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace

from .config import LiveConfig
from .engine import LiveEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable near-live CDN monitor")
    parser.add_argument("command", nargs="?", choices=("run", "doctor", "status"), default="run")
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
        handlers=[logging.FileHandler(config.log_path, encoding="utf-8"), logging.StreamHandler()],
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
        }
        print(json.dumps(checks, indent=2))
        return int(
            (args.no_sync and not checks["spool_exists"])
            or (not args.no_sync and not checks["rclone_exists"])
        )
    engine = LiveEngine(config, sync_enabled=not args.no_sync)
    if args.command == "status":
        print(json.dumps(engine.publish_snapshot(), indent=2))
        return 0
    engine.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
