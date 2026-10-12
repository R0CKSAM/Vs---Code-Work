"""
heartbeat.py – Heartbeat Tracker for FanCode Monitor Process & Pipeline Health (Phase 11).

Maintains a local heartbeat file so health checks can distinguish between:
- Process alive vs. process dead
- Pipeline actively progressing vs. hung/stuck in a stage
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Manages writing, reading, and evaluating the local monitor heartbeat."""

    def __init__(self, filepath: Optional[str] = None) -> None:
        self.filepath = Path(filepath or getattr(settings, "HEARTBEAT_FILE", "data/monitor.heartbeat"))
        self._start_time = time.time()

    def touch(
        self,
        stage: Optional[str] = None,
        cycle: Optional[int] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Updates the heartbeat file with current timestamp and execution state."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "pid": os.getpid(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage or "idle",
                "cycle": cycle or 0,
                "run_id": run_id,
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }
            # Atomic write via temp file rename
            temp_path = self.filepath.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.filepath)
        except Exception as e:
            logger.debug("Failed to update heartbeat: %s", e)

    def read(self) -> Optional[Dict[str, Any]]:
        """Reads current heartbeat metadata from disk."""
        if not self.filepath.exists():
            return None
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def is_fresh(self, max_age_seconds: int = 60) -> bool:
        """Returns True if the heartbeat was touched recently within max_age_seconds."""
        data = self.read()
        if not data:
            return False
        ts_str = data.get("timestamp")
        if not ts_str:
            return False
        try:
            ts = datetime.fromisoformat(ts_str)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age <= max_age_seconds
        except Exception:
            return False

    def clear(self) -> None:
        """Removes the heartbeat file."""
        try:
            if self.filepath.exists():
                self.filepath.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Failed to delete heartbeat file: %s", e)


# Global heartbeat manager instance
heartbeat = HeartbeatManager()
