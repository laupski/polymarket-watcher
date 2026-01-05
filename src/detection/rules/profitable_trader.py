"""Profitable trader detector - flags wallets with suspicious profitability patterns."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from ...api import DataApiClient, Trade
from ...db import Alert, Repository

logger = logging.getLogger(__name__)


@dataclass
class ProfitableTraderConfig:
    """Configuration for the profitable trader detector."""

    # Minimum trades to analyze a wallet
    min_trades_for_analysis: int
    # Minimum profit factor to flag (gross_profit / gross_loss)
    min_profit_factor: float
    # Minimum win rate to flag
    min_win_rate: float
    # Minimum trades per day to be considered high-frequency
    high_frequency_threshold: int
    # Cache TTL for wallet stats
    cache_ttl_hours: int


@dataclass
class WalletStats:
    """Tracked statistics for a wallet."""

    address: str
    trades: list[Trade]
    first_seen: datetime
    last_seen: datetime

    # Computed metrics
    total_volume: float = 0
    estimated_pnl: float = 0
    win_count: int = 0
    loss_count: int = 0

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return self.win_count / total if total > 0 else 0

    @property
    def trades_per_day(self) -> float:
        days = max(1, (self.last_seen - self.first_seen).days + 1)
        return self.trade_count / days


class ProfitableTraderDetector:
    """
    Detects wallets exhibiting suspicious profitability patterns.

    This detector tracks wallets over time and flags those that show:
    1. Consistently high win rates
    2. High profit factors
    3. High-frequency trading patterns

    These patterns may indicate:
    - Sophisticated trading bots
    - Insider information
    - Market manipulation
    """

    ALERT_TYPE = "profitable_trader"

    def __init__(
        self,
        config: ProfitableTraderConfig,
        repository: Repository,
        data_api: DataApiClient,
    ):
        self.config = config
        self.repository = repository
        self.data_api = data_api

        # In-memory tracking of wallet activity
        self._wallet_stats: dict[str, WalletStats] = {}
        self._position_tracker: dict[str, dict[str, list[Trade]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._alerted_wallets: set[str] = set()  # Avoid duplicate alerts

    async def analyze(self, trade: Trade) -> Alert | None:
        """
        Analyze a trade and update wallet statistics.

        Args:
            trade: The trade to analyze

        Returns:
            Alert if suspicious pattern detected, None otherwise
        """
        wallet = trade.proxy_wallet
        if not wallet:
            return None

        # Update wallet stats
        stats = self._update_wallet_stats(wallet, trade)

        # Track position for P&L estimation
        self._track_position(wallet, trade)

        # Check if we have enough data to analyze
        if stats.trade_count < self.config.min_trades_for_analysis:
            return None

        # Skip if already alerted for this wallet
        if wallet in self._alerted_wallets:
            return None

        # Check for suspicious patterns
        alert = self._check_for_anomalies(stats, trade)

        if alert:
            self._alerted_wallets.add(wallet)

        return alert

    def _update_wallet_stats(self, wallet: str, trade: Trade) -> WalletStats:
        """Update statistics for a wallet."""
        if wallet not in self._wallet_stats:
            self._wallet_stats[wallet] = WalletStats(
                address=wallet,
                trades=[],
                first_seen=trade.timestamp,
                last_seen=trade.timestamp,
            )

        stats = self._wallet_stats[wallet]
        stats.trades.append(trade)
        stats.last_seen = trade.timestamp
        stats.total_volume += trade.usd_value

        # Keep only recent trades to limit memory
        max_trades = 1000
        if len(stats.trades) > max_trades:
            stats.trades = stats.trades[-max_trades:]

        return stats

    def _track_position(self, wallet: str, trade: Trade):
        """Track positions to estimate P&L."""
        market_key = f"{trade.condition_id}:{trade.outcome}"
        positions = self._position_tracker[wallet][market_key]

        if trade.side == "BUY":
            positions.append(trade)
        elif trade.side == "SELL" and positions:
            # Match with oldest buy (FIFO)
            buy_trade = positions.pop(0)

            # Estimate P&L from the round trip
            pnl = (trade.price - buy_trade.price) * min(trade.size, buy_trade.size)

            stats = self._wallet_stats.get(wallet)
            if stats:
                stats.estimated_pnl += pnl
                if pnl > 0:
                    stats.win_count += 1
                elif pnl < 0:
                    stats.loss_count += 1

    def _check_for_anomalies(
        self, stats: WalletStats, latest_trade: Trade
    ) -> Alert | None:
        """Check if wallet stats indicate suspicious patterns."""
        reasons = []

        # Check win rate
        if stats.win_rate >= self.config.min_win_rate:
            reasons.append(f"High win rate: {stats.win_rate * 100:.1f}%")

        # Check profit factor
        if stats.win_count > 0 and stats.loss_count > 0:
            # Approximate profit factor from win/loss ratio
            # (In reality we'd need actual P&L amounts, but this is an estimate)
            approx_profit_factor = stats.win_count / stats.loss_count
            if approx_profit_factor >= self.config.min_profit_factor:
                reasons.append(f"High profit factor: {approx_profit_factor:.2f}x")

        # Check trading frequency
        if stats.trades_per_day >= self.config.high_frequency_threshold:
            reasons.append(
                f"High-frequency trading: {stats.trades_per_day:.0f} trades/day"
            )

        # Need at least 2 reasons to flag
        if len(reasons) < 2:
            return None

        return Alert(
            id=None,
            created_at=datetime.now(),
            alert_type=self.ALERT_TYPE,
            wallet_address=stats.address,
            trade_size_usd=stats.total_volume,
            wallet_trade_count=stats.trade_count,
            market_id=latest_trade.condition_id,
            market_name=latest_trade.slug,
            outcome=latest_trade.outcome,
            side=latest_trade.side,
            transaction_hash=latest_trade.transaction_hash,
            details={
                "reasons": reasons,
                "win_rate": stats.win_rate,
                "trades_per_day": stats.trades_per_day,
                "estimated_pnl": stats.estimated_pnl,
                "total_volume": stats.total_volume,
                "trade_count": stats.trade_count,
                "first_seen": stats.first_seen.isoformat(),
            },
        )

    def get_tracked_wallets(self) -> list[WalletStats]:
        """Get all tracked wallet statistics."""
        return list(self._wallet_stats.values())

    def get_suspicious_wallets(self) -> list[WalletStats]:
        """Get wallets that meet suspicious criteria."""
        suspicious = []
        for stats in self._wallet_stats.values():
            if stats.trade_count < self.config.min_trades_for_analysis:
                continue

            if stats.win_rate >= self.config.min_win_rate:
                suspicious.append(stats)
            elif stats.trades_per_day >= self.config.high_frequency_threshold:
                suspicious.append(stats)

        return sorted(suspicious, key=lambda s: s.estimated_pnl, reverse=True)
