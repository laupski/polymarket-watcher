"""Concentrated betting detector - flags accounts with high volume but few trades."""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from ...api import DataApiClient
from ...db import Alert, Repository

logger = logging.getLogger(__name__)


@dataclass
class ConcentratedBettingConfig:
    """Configuration for the concentrated betting detector."""

    min_volume_usd: float  # Minimum total volume to flag
    max_trades_for_concentration: int  # Max trades to be considered concentrated
    min_avg_trade_usd: float  # Minimum average trade size
    cache_ttl_hours: int  # How long to cache wallet history


@dataclass
class WalletAnalysis:
    """Analysis results for a wallet."""

    address: str
    total_trades: int
    total_volume: float
    avg_trade_size: float
    unique_markets: int
    top_market_concentration: float  # % of volume in top market
    market_titles: list[str]


class ConcentratedBettingDetector:
    """
    Detects accounts with high volume concentrated in few trades.

    This detector flags wallets where:
    1. Total volume exceeds threshold (e.g., $10,000)
    2. Trade count is below threshold (e.g., < 25 trades)
    3. Average trade size is high (e.g., > $1,000)
    """

    ALERT_TYPE = "concentrated_betting"

    def __init__(
        self,
        config: ConcentratedBettingConfig,
        repository: Repository,
        data_api: DataApiClient,
    ):
        self.config = config
        self.repository = repository
        self.data_api = data_api
        self._analyzed_wallets: set[str] = set()

    async def analyze_wallet(self, address: str) -> Alert | None:
        """
        Analyze a wallet for concentrated betting patterns.

        Args:
            address: Wallet address to analyze

        Returns:
            Alert if anomaly detected, None otherwise
        """
        # Skip if already analyzed this session
        if address.lower() in self._analyzed_wallets:
            return None

        self._analyzed_wallets.add(address.lower())

        try:
            analysis = await self._get_wallet_analysis(address)
        except Exception as e:
            logger.error(f"Error analyzing wallet {address[:10]}...: {e}")
            return None

        # Check criteria
        if analysis.total_trades > self.config.max_trades_for_concentration:
            logger.debug(
                f"Wallet {address[:10]}... has {analysis.total_trades} trades, "
                f"above threshold of {self.config.max_trades_for_concentration}"
            )
            return None

        if analysis.total_volume < self.config.min_volume_usd:
            logger.debug(
                f"Wallet {address[:10]}... has ${analysis.total_volume:,.2f} volume, "
                f"below threshold of ${self.config.min_volume_usd:,.2f}"
            )
            return None

        if analysis.avg_trade_size < self.config.min_avg_trade_usd:
            logger.debug(
                f"Wallet {address[:10]}... avg trade ${analysis.avg_trade_size:,.2f}, "
                f"below threshold of ${self.config.min_avg_trade_usd:,.2f}"
            )
            return None

        # Create alert
        alert = Alert(
            id=None,
            created_at=datetime.now(),
            alert_type=self.ALERT_TYPE,
            wallet_address=address,
            trade_size_usd=analysis.total_volume,
            wallet_trade_count=analysis.total_trades,
            market_id=None,
            market_name=", ".join(analysis.market_titles[:3]),
            outcome=None,
            side=None,
            transaction_hash=None,
            details={
                "total_volume": analysis.total_volume,
                "avg_trade_size": analysis.avg_trade_size,
                "unique_markets": analysis.unique_markets,
                "top_market_concentration": analysis.top_market_concentration,
                "markets": analysis.market_titles[:5],
            },
        )

        logger.info(
            f"ALERT: Concentrated betting detected for {address[:10]}... - "
            f"${analysis.total_volume:,.2f} across {analysis.total_trades} trades"
        )

        return alert

    async def _get_wallet_analysis(self, address: str) -> WalletAnalysis:
        """
        Get detailed analysis of a wallet's trading patterns.

        Args:
            address: Wallet address

        Returns:
            WalletAnalysis with trading statistics
        """
        summary = await self.data_api.get_wallet_activity(
            address,
            limit=500,
            activity_type="TRADE",
        )

        trades = summary.activities
        total_volume = sum(t.usd_size for t in trades)
        avg_trade = total_volume / len(trades) if trades else 0

        # Analyze market concentration
        market_volumes: Counter[str] = Counter()
        market_titles: dict[str, str] = {}

        for trade in trades:
            market_id = trade.market_id or "unknown"
            market_volumes[market_id] += trade.usd_size
            if trade.market_title:
                market_titles[market_id] = trade.market_title

        unique_markets = len(market_volumes)
        top_market_volume = market_volumes.most_common(1)[0][1] if market_volumes else 0
        top_concentration = (
            (top_market_volume / total_volume * 100) if total_volume else 0
        )

        # Get titles of top markets
        top_market_ids = [m[0] for m in market_volumes.most_common(5)]
        titles = [market_titles.get(mid, mid[:20]) for mid in top_market_ids]

        return WalletAnalysis(
            address=address,
            total_trades=len(trades),
            total_volume=total_volume,
            avg_trade_size=avg_trade,
            unique_markets=unique_markets,
            top_market_concentration=top_concentration,
            market_titles=titles,
        )
