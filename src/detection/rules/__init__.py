"""Detection rules."""

from .concentrated_betting import ConcentratedBettingConfig, ConcentratedBettingDetector
from .low_history import LowHistoryDetector, LowHistoryDetectorConfig
from .profitable_trader import ProfitableTraderConfig, ProfitableTraderDetector

__all__ = [
    "ConcentratedBettingDetector",
    "ConcentratedBettingConfig",
    "LowHistoryDetector",
    "LowHistoryDetectorConfig",
    "ProfitableTraderDetector",
    "ProfitableTraderConfig",
]
