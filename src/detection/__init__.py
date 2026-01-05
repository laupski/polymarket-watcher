"""Detection engine and rules."""

from .engine import DetectionEngine, Detector
from .rules import (
    LowHistoryDetector,
    LowHistoryDetectorConfig,
    ProfitableTraderConfig,
    ProfitableTraderDetector,
)

__all__ = [
    "DetectionEngine",
    "Detector",
    "LowHistoryDetector",
    "LowHistoryDetectorConfig",
    "ProfitableTraderDetector",
    "ProfitableTraderConfig",
]
