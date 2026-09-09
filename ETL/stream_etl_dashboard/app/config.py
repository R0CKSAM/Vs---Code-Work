from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _stream_aliases() -> dict[str, str]:
    result = {}
    raw = os.getenv("STREAM_ALIASES", "vglive-274906:vglive-sk-274906")
    for item in raw.split(","):
        if ":" in item:
            dashboard_name, source_segment = item.split(":", 1)
            result[dashboard_name.strip()] = source_segment.strip()
    return result


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    db_path: Path = PROJECT_ROOT / "data" / "analytics.db"
    rclone_exe: str = os.getenv("RCLONE_EXE", r"D:\cloner\rclone.exe")
    rclone_remote: str = os.getenv(
        "RCLONE_REMOTE", "veto:veto-stream-logs/veto-stream-logs"
    )
    local_log_root: Path = Path(
        os.getenv("LOCAL_LOG_ROOT", r"D:\Veto Logs Backup\Veto Stream Logs")
    )
    streams: tuple[str, ...] = tuple(
        x.strip() for x in os.getenv("STREAMS", "vglive-274906,upgovlive").split(",")
        if x.strip()
    )
    stream_aliases: dict[str, str] = field(default_factory=_stream_aliases)
    sync_interval_seconds: int = int(os.getenv("SYNC_INTERVAL_SECONDS", "10"))
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "5"))
    finalize_after_seconds: int = int(os.getenv("FINALIZE_AFTER_SECONDS", "90"))
    parser_workers: int = int(os.getenv("PARSER_WORKERS", "8"))
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8788"))


settings = Settings()
