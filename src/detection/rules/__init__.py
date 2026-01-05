"""Detection rules."""

from .low_history import LowHistoryDetector, LowHistoryDetectorConfig
from .profitable_trader import ProfitableTraderConfig, ProfitableTraderDetector

__all__ = [
    "LowHistoryDetector",
    "LowHistoryDetectorConfig",
    "ProfitableTraderDetector",
    "ProfitableTraderConfig",
]
