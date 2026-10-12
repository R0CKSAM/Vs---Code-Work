"""
models.py – Data models, enums, and result containers for Pipeline Orchestrator (Phase 10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


class StageName(str, Enum):
    SCHEDULE = "schedule"
    SPORTS = "sports"
    TOURS = "tours"
    MATCH_DETAIL = "match_detail"
    LIVE_NOW = "live_now"
    VIDEOS = "videos"
    CHANGE_DETECTION = "change_detection"
    NOTIFICATIONS = "notifications"
    DISCOVERY = "discovery"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PipelineStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ExitCode(IntEnum):
    SUCCESS = 0
    PARTIAL = 1
    CONFIG_ERROR = 2
    LOCKED = 3
    FATAL = 4
    INTERRUPTED = 130


@dataclass
class StageResult:
    """Detailed outcome of a single pipeline stage execution."""
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    changes_detected: int = 0
    notifications_sent: int = 0
    retries_attempted: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "records_processed": self.records_processed,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "changes_detected": self.changes_detected,
            "notifications_sent": self.notifications_sent,
            "retries_attempted": self.retries_attempted,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class PipelineRunResult:
    """Comprehensive summary of an entire monitor pipeline execution."""
    run_id: Optional[int] = None
    trigger_type: str = "manual"  # manual, scheduled, retry
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    stages: Dict[str, StageResult] = field(default_factory=dict)
    is_dry_run: bool = False
    error_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> ExitCode:
        if self.status == PipelineStatus.SUCCESS:
            return ExitCode.SUCCESS
        if self.status == PipelineStatus.SKIPPED:
            return ExitCode.LOCKED
        if self.status == PipelineStatus.PARTIAL:
            return ExitCode.PARTIAL
        return ExitCode.FATAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trigger_type": self.trigger_type,
            "status": self.status.value,
            "exit_code": int(self.exit_code),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "is_dry_run": self.is_dry_run,
            "error_summary": self.error_summary,
            "stages": {name: res.to_dict() for name, res in self.stages.items()},
            "metadata": self.metadata,
        }
