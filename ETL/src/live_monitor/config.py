from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


ETL_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser()


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class LiveConfig:
    """Runtime configuration with portable defaults and environment overrides."""

    remote_base: str = field(
        default_factory=lambda: os.getenv(
            "VETO_LIVE_REMOTE", "veto:veto-stream-logs/veto-stream-logs"
        )
    )
    spool_root: Path = field(
        default_factory=lambda: _env_path(
            "VETO_LIVE_SPOOL", ETL_ROOT / "data" / "live_spool"
        )
    )
    state_dir: Path = field(
        default_factory=lambda: _env_path(
            "VETO_LIVE_STATE_DIR", ETL_ROOT / "output" / "live_monitor"
        )
    )
    rclone_exe: Path = field(
        default_factory=lambda: _env_path(
            "VETO_RCLONE_EXE", ETL_ROOT / "tools" / "rclone" / "rclone.exe"
        )
    )
    watched_paths: tuple[str, ...] = field(
        default_factory=lambda: _env_list(
            "VETO_LIVE_WATCHED_PATHS", ("vglive-274906", "upgovlive")
        )
    )
    scan_seconds: float = 2.0
    snapshot_seconds: float = 5.0
    sync_seconds: float = 30.0
    full_scan_seconds: float = 1800.0
    full_sync_seconds: float = 1800.0
    parse_workers: int = max(2, min(6, os.cpu_count() or 4))
    # rclone publishes each .gz only after its temporary download is complete.
    # One observation therefore avoids an unnecessary second full directory scan.
    stable_observations: int = 1
    stale_processing_seconds: int = 300
    recent_hours: int = 3
    # Zero means today's IST calendar day, not a moving 24-hour window.
    dashboard_minutes: int = field(
        default_factory=lambda: max(0, int(os.getenv("VETO_LIVE_DASHBOARD_MINUTES", "0")))
    )
    health_max_lag_seconds: int = field(
        default_factory=lambda: int(os.getenv("VETO_LIVE_MAX_LAG_SECONDS", "600"))
    )
    http_host: str = field(
        default_factory=lambda: os.getenv("VETO_LIVE_HTTP_HOST", "127.0.0.1")
    )
    http_port: int = field(
        default_factory=lambda: int(os.getenv("VETO_LIVE_HTTP_PORT", "8790"))
    )

    @property
    def database_path(self) -> Path:
        return self.state_dir / "live_monitor.sqlite3"

    @property
    def snapshot_path(self) -> Path:
        return self.state_dir / "live_state.json"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "live_monitor.log"
