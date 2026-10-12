"""
app.change_detection – FanCode Change Detection Engine (Phase 8).
"""

from app.change_detection.classifier import ChangeClassifier
from app.change_detection.comparator import StateComparator
from app.change_detection.detector import ChangeDetector
from app.change_detection.models import (
    ChangeDetectionResult,
    ChangeType,
    EntityType,
    ProposedChangeEvent,
    Severity,
)

__all__ = [
    "ChangeClassifier",
    "StateComparator",
    "ChangeDetector",
    "ChangeDetectionResult",
    "ChangeType",
    "EntityType",
    "ProposedChangeEvent",
    "Severity",
]
