"""
app.monitor – FanCode Scheduler & Continuous Monitoring Engine (Phase 10).
"""

from typing import Any

from app.monitor.exceptions import (
    ErrorAction,
    ErrorCategory,
    FatalPipelineError,
    LockAcquisitionError,
    LockError,
    MonitorError,
    StageExecutionError,
    StageTimeoutError,
    classify_error,
)
from app.monitor.health import MonitorHealth
from app.monitor.lock import MonitorLock
from app.monitor.models import (
    ExitCode,
    PipelineRunResult,
    PipelineStatus,
    StageName,
    StageResult,
    StageStatus,
)

__all__ = [
    "MonitorRunner",
    "MonitorPipeline",
    "MonitorLock",
    "MonitorHealth",
    "PipelineContext",
    "BaseStage",
    "ScheduleStage",
    "SportsToursStage",
    "MatchDetailStage",
    "LiveNowStage",
    "VideosStage",
    "ChangeDetectionStage",
    "NotificationStage",
    "DiscoveryStage",
    "StageName",
    "StageStatus",
    "PipelineStatus",
    "ExitCode",
    "StageResult",
    "PipelineRunResult",
    "MonitorError",
    "LockError",
    "LockAcquisitionError",
    "FatalPipelineError",
    "StageExecutionError",
    "StageTimeoutError",
    "ErrorAction",
    "ErrorCategory",
    "classify_error",
]


def __getattr__(name: str) -> Any:
    if name == "MonitorPipeline":
        from app.monitor.pipeline import MonitorPipeline
        return MonitorPipeline
    elif name == "MonitorRunner":
        from app.monitor.runner import MonitorRunner
        return MonitorRunner
    elif name in (
        "BaseStage",
        "ChangeDetectionStage",
        "DiscoveryStage",
        "LiveNowStage",
        "MatchDetailStage",
        "NotificationStage",
        "PipelineContext",
        "ScheduleStage",
        "SportsToursStage",
        "VideosStage",
    ):
        import app.monitor.stages as stages
        return getattr(stages, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

