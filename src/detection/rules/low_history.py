"""Low history detector - flags large trades from wallets with minimal trade history."""

import logging
from dataclasses import dataclass
from datetime import datetime

from ...api import DataApiClient, Trade
from ...db import Alert, Repository

logger = logging.getLogger(__name__)


@dataclass
class LowHistoryDetectorConfig:
    """Configuration for the low history detector."""

    large_trade_usd: float  # Minimum trade size to analyze
    low_history_threshold: int  # Max trades to be considered "low history"
    cache_ttl_hours: int  # How long to cache wallet history


class LowHistoryDetector:
    """
    Detects large trades from wallets with minimal trading history.

    This detector flags trades where:
    1. Trade value exceeds the configured threshold (e.g., $20,000)
    2. The wallet has fewer trades than the low history threshold (e.g., < 10)
    """

    ALERT_TYPE = "low_history_large_trade"

    def __init__(
        self,
        config: LowHistoryDetectorConfig,
        repository: Repository,
        data_api: DataApiClient,
    ):
        self.config = config
        self.repository = repository
        self.data_api = data_api

    async def analyze(self, trade: Trade) -> Alert | None:
        """
        Analyze a trade for anomalous behavior.

        Args:
            trade: The trade to analyze

        Returns:
            Alert if anomaly detected, None otherwise
        """
        # Calculate USD value
        usd_value = trade.usd_value

        # Skip if trade is below threshold
        if usd_value < self.config.large_trade_usd:
            return None

        logger.debug(
            f"Large trade detected: ${usd_value:,.2f} from {trade.proxy_wallet[:10]}..."
        )

        # Get wallet trade count
        trade_count = await self._get_wallet_trade_count(trade.proxy_wallet)

        # Check if wallet has low history
        if trade_count >= self.config.low_history_threshold:
            logger.debug(
                f"Wallet {trade.proxy_wallet[:10]}... has {trade_count} trades, "
                f"above threshold of {self.config.low_history_threshold}"
            )
            return None

        # Create alert
        alert = Alert(
            id=None,
            created_at=datetime.now(),
            alert_type=self.ALERT_TYPE,
            wallet_address=trade.proxy_wallet,
            trade_size_usd=usd_value,
            wallet_trade_count=trade_count,
            market_id=trade.condition_id,
            market_name=trade.slug,  # Will be enriched later if needed
            outcome=trade.outcome,
            side=trade.side,
            transaction_hash=trade.transaction_hash,
            details={
                "price": trade.price,
                "size": trade.size,
                "event_slug": trade.event_slug,
                "pseudonym": trade.pseudonym,
            },
        )

        return alert

    async def _get_wallet_trade_count(self, address: str) -> int:
        """
        Get the trade count for a wallet, using cache when available.

        Args:
            address: Wallet address

        Returns:
            Number of historical trades
        """
        # Check cache first
        cached = await self.repository.get_cached_wallet_if_fresh(
            address,
            max_age_hours=self.config.cache_ttl_hours,
        )

        if cached is not None:
            logger.debug(
                f"Cache hit for {address[:10]}...: {cached.trade_count} trades"
            )
            return cached.trade_count

        # Fetch from API
        logger.debug(f"Fetching trade history for {address[:10]}...")

        try:
            summary = await self.data_api.get_wallet_activity(
                address,
                limit=500,
                activity_type="TRADE",
            )
            trade_count = summary.total_trades

            # Cache the result
            await self.repository.cache_wallet(
                address,
                trade_count,
                first_trade_at=summary.first_trade_at,
            )

            logger.debug(
                f"Fetched and cached: {address[:10]}... has {trade_count} trades"
            )
            return trade_count

        except Exception as e:
            logger.error(f"Error fetching wallet history for {address}: {e}")
            # Return a high number to avoid false positives on API errors
            return 999
