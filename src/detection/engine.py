"""Detection engine - orchestrates all detection rules."""

import logging
from typing import Protocol

from ..api import Trade
from ..db import Alert, Repository

logger = logging.getLogger(__name__)


class Detector(Protocol):
    """Protocol for detection rules."""

    ALERT_TYPE: str

    async def analyze(self, trade: Trade) -> Alert | None:
        """Analyze a trade and return an alert if anomaly detected."""
        ...


class DetectionEngine:
    """
    Orchestrates all detection rules and processes trades.

    The engine runs each detector against incoming trades and
    collects any alerts generated.
    """

    def __init__(
        self,
        repository: Repository,
        detectors: list[Detector] | None = None,
    ):
        self.repository = repository
        self.detectors: list[Detector] = detectors or []
        self._trade_count = 0
        self._alert_count = 0

    def add_detector(self, detector: Detector):
        """Add a detector to the engine."""
        self.detectors.append(detector)
        logger.info(f"Added detector: {detector.ALERT_TYPE}")

    async def process_trade(self, trade: Trade) -> list[Alert]:
        """
        Process a trade through all detectors.

        Args:
            trade: The trade to analyze

        Returns:
            List of alerts generated (may be empty)
        """
        self._trade_count += 1
        alerts: list[Alert] = []

        for detector in self.detectors:
            try:
                alert = await detector.analyze(trade)
                if alert:
                    # Save alert to database
                    alert_id = await self.repository.save_alert(alert)
                    alert.id = alert_id
                    alerts.append(alert)
                    self._alert_count += 1

            except Exception as e:
                logger.error(
                    f"Error in detector {detector.ALERT_TYPE}: {e}",
                    exc_info=True,
                )

        # Optionally save trade for historical analysis
        try:
            await self.repository.save_trade(
                transaction_hash=trade.transaction_hash,
                wallet_address=trade.proxy_wallet,
                market_id=trade.condition_id,
                market_slug=trade.slug,
                outcome=trade.outcome,
                side=trade.side,
                size=trade.size,
                price=trade.price,
                usd_value=trade.usd_value,
                timestamp=trade.timestamp,
            )
        except Exception as e:
            logger.debug(f"Error saving trade: {e}")

        # Update wallet cache if we have it
        if trade.proxy_wallet:
            await self.repository.increment_wallet_trade_count(trade.proxy_wallet)

        return alerts

    @property
    def stats(self) -> dict:
        """Get engine statistics."""
        return {
            "trades_processed": self._trade_count,
            "alerts_generated": self._alert_count,
            "detectors_active": len(self.detectors),
        }
