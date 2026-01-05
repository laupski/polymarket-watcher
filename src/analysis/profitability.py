"""Profitability analyzer for Polymarket wallets."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median, stdev

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """A single trade record."""

    timestamp: datetime
    market_slug: str
    market_title: str
    outcome: str
    side: str  # BUY or SELL
    size: float
    price: float
    usd_size: float
    transaction_hash: str
    asset: str


@dataclass
class MarketPosition:
    """Aggregated position in a market."""

    market_slug: str
    market_title: str
    outcome: str
    total_bought: float
    total_sold: float
    avg_buy_price: float
    avg_sell_price: float
    net_position: float
    realized_pnl: float
    trade_count: int
    first_trade: datetime
    last_trade: datetime


@dataclass
class StrategyInsights:
    """Detected trading strategy patterns."""

    primary_strategy: str
    confidence: float
    characteristics: list[str]

    # Trading patterns
    avg_hold_time_hours: float | None
    trades_per_day: float
    avg_trade_size_usd: float
    median_trade_size_usd: float

    # Market preferences
    favorite_categories: list[tuple[str, int]]  # (category, count)
    prefers_favorites: bool  # Tends to buy likely outcomes
    prefers_underdogs: bool  # Tends to buy unlikely outcomes

    # Timing patterns
    most_active_hours: list[int]  # Hours of day (UTC)
    weekend_trader: bool

    # Risk profile
    position_sizing_consistent: bool
    max_position_usd: float
    avg_positions_concurrent: float


@dataclass
class WalletProfile:
    """Complete profile of a wallet's trading activity."""

    address: str
    username: str | None

    # Overall stats
    total_pnl: float
    total_volume: float
    total_trades: int
    win_rate: float
    profit_factor: float  # gross_profit / gross_loss

    # Performance metrics
    avg_profit_per_trade: float
    best_trade_pnl: float
    worst_trade_pnl: float
    sharpe_ratio: float | None  # Risk-adjusted return

    # Time analysis
    first_trade_at: datetime | None
    last_trade_at: datetime | None
    active_days: int

    # Positions breakdown
    positions: list[MarketPosition] = field(default_factory=list)

    # Strategy analysis
    strategy: StrategyInsights | None = None


@dataclass
class TradeAnalysis:
    """Analysis results for display."""

    profile: WalletProfile
    warnings: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


class ProfitabilityAnalyzer:
    """Analyzes wallet trading history for profitability patterns."""

    def __init__(self, data_api_base: str = "https://data-api.polymarket.com"):
        self.data_api_base = data_api_base.rstrip("/")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self._client.aclose()

    async def analyze_wallet(
        self,
        address: str,
        username: str | None = None,
        max_trades: int | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> TradeAnalysis:
        """
        Perform comprehensive analysis of a wallet's trading history.

        Args:
            address: Wallet address (0x...)
            username: Optional username for display
            max_trades: Maximum trades to fetch (None = fetch all)
            start_timestamp: Only fetch trades after this Unix timestamp
            end_timestamp: Only fetch trades before this Unix timestamp

        Returns:
            TradeAnalysis with full profile and insights
        """
        logger.info(f"Analyzing wallet: {address[:10]}... ({username or 'unknown'})")

        # Fetch trades
        trades = await self._fetch_all_trades(
            address,
            max_trades=max_trades,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
        )
        logger.info(f"Fetched {len(trades)} trades")

        if not trades:
            return TradeAnalysis(
                profile=WalletProfile(
                    address=address,
                    username=username,
                    total_pnl=0,
                    total_volume=0,
                    total_trades=0,
                    win_rate=0,
                    profit_factor=0,
                    avg_profit_per_trade=0,
                    best_trade_pnl=0,
                    worst_trade_pnl=0,
                    sharpe_ratio=None,
                    first_trade_at=None,
                    last_trade_at=None,
                    active_days=0,
                ),
                warnings=["No trades found for this wallet"],
            )

        # Build positions from trades
        positions = self._build_positions(trades)

        # Calculate overall metrics
        profile = self._calculate_profile(address, username, trades, positions)

        # Detect strategy patterns
        profile.strategy = self._detect_strategy(trades, positions)

        # Generate warnings and anomalies
        warnings, anomalies = self._detect_anomalies(profile, trades)

        return TradeAnalysis(
            profile=profile,
            warnings=warnings,
            anomalies=anomalies,
        )

    async def _fetch_all_trades(
        self,
        address: str,
        max_trades: int | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
    ) -> list[TradeRecord]:
        """Fetch trades for a wallet with pagination."""
        trades = []
        offset = 0
        limit = 500

        while max_trades is None or len(trades) < max_trades:
            params = {
                "user": address,
                "limit": limit,
                "offset": offset,
                "type": "TRADE",
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            }

            if start_timestamp:
                params["start"] = start_timestamp
            if end_timestamp:
                params["end"] = end_timestamp

            try:
                response = await self._client.get(
                    f"{self.data_api_base}/activity",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for item in data:
                    try:
                        ts = item.get("timestamp")
                        if not ts:
                            continue
                        # Handle both Unix timestamp (int) and ISO string
                        if isinstance(ts, (int, float)):
                            timestamp = datetime.fromtimestamp(ts)
                        else:
                            timestamp = datetime.fromisoformat(
                                str(ts).replace("Z", "+00:00")
                            )

                        trade = TradeRecord(
                            timestamp=timestamp,
                            market_slug=item.get("slug", ""),
                            market_title=item.get("title", "Unknown"),
                            outcome=item.get("outcome", ""),
                            side=item.get("side", ""),
                            size=float(item.get("size", 0)),
                            price=float(item.get("price", 0))
                            if item.get("price")
                            else 0,
                            usd_size=float(item.get("usdcSize", 0)),
                            transaction_hash=item.get("transactionHash", ""),
                            asset=item.get("asset", ""),
                        )
                        trades.append(trade)
                    except Exception as e:
                        logger.debug(f"Error parsing trade: {e}")
                        continue

                if len(data) < limit:
                    break

                offset += limit
                print(f"  Fetched {len(trades)} trades...", flush=True)

            except httpx.HTTPStatusError as e:
                logger.error(f"API error fetching trades: {e}")
                break

        return trades

    def _build_positions(self, trades: list[TradeRecord]) -> list[MarketPosition]:
        """Aggregate trades into market positions."""
        # Group by market and outcome
        position_map: dict[tuple[str, str], list[TradeRecord]] = defaultdict(list)

        for trade in trades:
            key = (trade.market_slug, trade.outcome)
            position_map[key].append(trade)

        positions = []
        for (market_slug, outcome), market_trades in position_map.items():
            buys = [t for t in market_trades if t.side == "BUY"]
            sells = [t for t in market_trades if t.side == "SELL"]

            total_bought = sum(t.size for t in buys)
            total_sold = sum(t.size for t in sells)

            avg_buy_price = (
                sum(t.price * t.size for t in buys) / total_bought
                if total_bought > 0
                else 0
            )
            avg_sell_price = (
                sum(t.price * t.size for t in sells) / total_sold
                if total_sold > 0
                else 0
            )

            # Realized P&L from round trips
            matched_size = min(total_bought, total_sold)
            realized_pnl = (
                matched_size * (avg_sell_price - avg_buy_price)
                if matched_size > 0
                else 0
            )

            positions.append(
                MarketPosition(
                    market_slug=market_slug,
                    market_title=market_trades[0].market_title,
                    outcome=outcome,
                    total_bought=total_bought,
                    total_sold=total_sold,
                    avg_buy_price=avg_buy_price,
                    avg_sell_price=avg_sell_price,
                    net_position=total_bought - total_sold,
                    realized_pnl=realized_pnl,
                    trade_count=len(market_trades),
                    first_trade=min(t.timestamp for t in market_trades),
                    last_trade=max(t.timestamp for t in market_trades),
                )
            )

        return sorted(positions, key=lambda p: abs(p.realized_pnl), reverse=True)

    def _calculate_profile(
        self,
        address: str,
        username: str | None,
        trades: list[TradeRecord],
        positions: list[MarketPosition],
    ) -> WalletProfile:
        """Calculate overall wallet profile metrics."""
        total_volume = sum(t.usd_size for t in trades)

        # Calculate P&L from positions
        total_realized_pnl = sum(p.realized_pnl for p in positions)

        # Win/loss tracking
        winning_positions = [p for p in positions if p.realized_pnl > 0]
        losing_positions = [p for p in positions if p.realized_pnl < 0]

        gross_profit = sum(p.realized_pnl for p in winning_positions)
        gross_loss = abs(sum(p.realized_pnl for p in losing_positions))

        win_rate = len(winning_positions) / len(positions) if positions else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Trade-level stats
        pnl_per_trade = [
            p.realized_pnl / p.trade_count for p in positions if p.trade_count > 0
        ]
        avg_profit_per_trade = mean(pnl_per_trade) if pnl_per_trade else 0

        best_trade = max((p.realized_pnl for p in positions), default=0)
        worst_trade = min((p.realized_pnl for p in positions), default=0)

        # Sharpe ratio approximation
        if len(pnl_per_trade) > 1:
            try:
                returns_std = stdev(pnl_per_trade)
                sharpe_ratio = (
                    (avg_profit_per_trade / returns_std) if returns_std > 0 else None
                )
            except:
                sharpe_ratio = None
        else:
            sharpe_ratio = None

        # Time analysis
        timestamps = [t.timestamp for t in trades]
        first_trade = min(timestamps) if timestamps else None
        last_trade = max(timestamps) if timestamps else None

        unique_days = len(set(t.timestamp.date() for t in trades))

        return WalletProfile(
            address=address,
            username=username,
            total_pnl=total_realized_pnl,
            total_volume=total_volume,
            total_trades=len(trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_profit_per_trade=avg_profit_per_trade,
            best_trade_pnl=best_trade,
            worst_trade_pnl=worst_trade,
            sharpe_ratio=sharpe_ratio,
            first_trade_at=first_trade,
            last_trade_at=last_trade,
            active_days=unique_days,
            positions=positions[:50],  # Top 50 positions
        )

    def _detect_strategy(
        self,
        trades: list[TradeRecord],
        positions: list[MarketPosition],
    ) -> StrategyInsights:
        """Detect trading strategy patterns."""

        # Trade sizing analysis
        trade_sizes = [t.usd_size for t in trades]
        avg_trade_size = mean(trade_sizes) if trade_sizes else 0
        median_trade_size = median(trade_sizes) if trade_sizes else 0
        max_trade_size = max(trade_sizes) if trade_sizes else 0

        # Position sizing consistency
        if len(trade_sizes) > 1:
            try:
                size_cv = (
                    stdev(trade_sizes) / mean(trade_sizes)
                    if mean(trade_sizes) > 0
                    else 0
                )
                position_sizing_consistent = (
                    size_cv < 1.0
                )  # CV < 1 means relatively consistent
            except:
                position_sizing_consistent = False
        else:
            position_sizing_consistent = True

        # Timing analysis
        hours = [t.timestamp.hour for t in trades]
        hour_counts = defaultdict(int)
        for h in hours:
            hour_counts[h] += 1
        most_active_hours = sorted(
            hour_counts.keys(), key=lambda h: hour_counts[h], reverse=True
        )[:3]

        weekdays = [t.timestamp.weekday() for t in trades]
        weekend_trades = sum(1 for w in weekdays if w >= 5)
        weekend_trader = weekend_trades / len(trades) > 0.3 if trades else False

        # Trades per day
        if trades:
            date_range = (
                max(t.timestamp for t in trades) - min(t.timestamp for t in trades)
            ).days + 1
            trades_per_day = len(trades) / date_range if date_range > 0 else len(trades)
        else:
            trades_per_day = 0

        # Market category preferences
        category_counts = defaultdict(int)
        for trade in trades:
            # Extract category from slug
            slug = trade.market_slug
            if (
                slug.startswith("nba-")
                or slug.startswith("nfl-")
                or slug.startswith("nhl-")
            ):
                category_counts["Sports"] += 1
            elif (
                "president" in slug
                or "election" in slug
                or "trump" in slug
                or "biden" in slug
            ):
                category_counts["Politics"] += 1
            elif (
                "crypto" in slug
                or "bitcoin" in slug
                or "eth" in slug
                or "updown" in slug
            ):
                category_counts["Crypto"] += 1
            else:
                category_counts["Other"] += 1

        favorite_categories = sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        )

        # Price preference (favorites vs underdogs)
        buy_prices = [t.price for t in trades if t.side == "BUY" and t.price > 0]
        if buy_prices:
            avg_buy_price = mean(buy_prices)
            prefers_favorites = avg_buy_price > 0.6
            prefers_underdogs = avg_buy_price < 0.4
        else:
            prefers_favorites = False
            prefers_underdogs = False

        # Hold time estimation (time between buy and sell in same market)
        hold_times = []
        for pos in positions:
            if pos.total_bought > 0 and pos.total_sold > 0:
                hold_time = (pos.last_trade - pos.first_trade).total_seconds() / 3600
                hold_times.append(hold_time)
        avg_hold_time = mean(hold_times) if hold_times else None

        # Strategy classification
        strategy, confidence, characteristics = self._classify_strategy(
            trades_per_day=trades_per_day,
            avg_hold_time=avg_hold_time,
            avg_trade_size=avg_trade_size,
            position_sizing_consistent=position_sizing_consistent,
            favorite_categories=favorite_categories,
            prefers_favorites=prefers_favorites,
            prefers_underdogs=prefers_underdogs,
            win_rate=len([p for p in positions if p.realized_pnl > 0]) / len(positions)
            if positions
            else 0,
        )

        return StrategyInsights(
            primary_strategy=strategy,
            confidence=confidence,
            characteristics=characteristics,
            avg_hold_time_hours=avg_hold_time,
            trades_per_day=trades_per_day,
            avg_trade_size_usd=avg_trade_size,
            median_trade_size_usd=median_trade_size,
            favorite_categories=favorite_categories,
            prefers_favorites=prefers_favorites,
            prefers_underdogs=prefers_underdogs,
            most_active_hours=most_active_hours,
            weekend_trader=weekend_trader,
            position_sizing_consistent=position_sizing_consistent,
            max_position_usd=max_trade_size,
            avg_positions_concurrent=len(positions)
            / max(1, len(set(t.timestamp.date() for t in trades))),
        )

    def _classify_strategy(
        self,
        trades_per_day: float,
        avg_hold_time: float | None,
        avg_trade_size: float,
        position_sizing_consistent: bool,
        favorite_categories: list[tuple[str, int]],
        prefers_favorites: bool,
        prefers_underdogs: bool,
        win_rate: float,
    ) -> tuple[str, float, list[str]]:
        """Classify the trading strategy based on patterns."""
        characteristics = []

        # High frequency trader
        if trades_per_day > 50:
            characteristics.append("High-frequency trader (50+ trades/day)")
        elif trades_per_day > 10:
            characteristics.append("Active trader (10-50 trades/day)")
        else:
            characteristics.append("Casual trader (<10 trades/day)")

        # Hold time
        if avg_hold_time is not None:
            if avg_hold_time < 1:
                characteristics.append("Scalper (holds < 1 hour)")
            elif avg_hold_time < 24:
                characteristics.append("Day trader (holds < 24 hours)")
            else:
                characteristics.append(
                    f"Swing trader (avg hold: {avg_hold_time:.1f} hours)"
                )

        # Position sizing
        if position_sizing_consistent:
            characteristics.append("Consistent position sizing")
        else:
            characteristics.append("Variable position sizing")

        # Market focus
        if favorite_categories:
            top_cat, top_count = favorite_categories[0]
            total = sum(c for _, c in favorite_categories)
            if top_count / total > 0.7:
                characteristics.append(
                    f"Specialist: {top_cat} ({top_count / total * 100:.0f}% of trades)"
                )
            else:
                characteristics.append("Diversified across categories")

        # Price preferences
        if prefers_favorites:
            characteristics.append("Prefers favorites (avg buy price > 60%)")
        elif prefers_underdogs:
            characteristics.append("Prefers underdogs (avg buy price < 40%)")
        else:
            characteristics.append("Balanced price targeting")

        # Win rate
        if win_rate > 0.7:
            characteristics.append(f"High win rate ({win_rate * 100:.1f}%)")
        elif win_rate > 0.5:
            characteristics.append(f"Profitable ({win_rate * 100:.1f}% win rate)")

        # Determine primary strategy
        if trades_per_day > 50 and avg_hold_time and avg_hold_time < 1:
            strategy = "High-Frequency Scalping"
            confidence = 0.85
        elif (
            trades_per_day > 20
            and favorite_categories
            and favorite_categories[0][0] == "Sports"
        ):
            strategy = "Sports Betting Arbitrage"
            confidence = 0.80
        elif (
            trades_per_day > 20
            and favorite_categories
            and favorite_categories[0][0] == "Crypto"
        ):
            strategy = "Crypto Price Speculation"
            confidence = 0.75
        elif avg_hold_time and avg_hold_time > 48 and win_rate > 0.6:
            strategy = "Informed Swing Trading"
            confidence = 0.70
        elif position_sizing_consistent and win_rate > 0.55:
            strategy = "Systematic Trading"
            confidence = 0.65
        else:
            strategy = "Mixed/Opportunistic"
            confidence = 0.50

        return strategy, confidence, characteristics

    def _detect_anomalies(
        self,
        profile: WalletProfile,
        trades: list[TradeRecord],
    ) -> tuple[list[str], list[str]]:
        """Detect suspicious patterns and anomalies."""
        warnings = []
        anomalies = []

        # Unusually high win rate
        if profile.win_rate > 0.75:
            anomalies.append(
                f"Exceptionally high win rate: {profile.win_rate * 100:.1f}%"
            )

        # Very high profit factor
        if profile.profit_factor > 3.0:
            anomalies.append(f"Very high profit factor: {profile.profit_factor:.2f}")

        # Consistent profitability with high volume
        if profile.total_volume > 1_000_000 and profile.total_pnl > 0:
            roi = profile.total_pnl / profile.total_volume * 100
            if roi > 0.5:
                anomalies.append(
                    f"Sustained {roi:.2f}% ROI on ${profile.total_volume:,.0f} volume"
                )

        # Trading at unusual hours consistently
        if profile.strategy and profile.strategy.most_active_hours:
            unusual_hours = [
                h for h in profile.strategy.most_active_hours if h < 6 or h > 22
            ]
            if len(unusual_hours) >= 2:
                warnings.append(f"Trades frequently at unusual hours: {unusual_hours}")

        # Extremely fast trading
        if profile.strategy and profile.strategy.trades_per_day > 100:
            anomalies.append(
                f"Extremely high trade frequency: {profile.strategy.trades_per_day:.0f}/day (likely bot)"
            )

        # Perfect or near-perfect streaks
        if profile.strategy:
            if profile.win_rate > 0.9 and profile.total_trades > 100:
                anomalies.append(
                    "Suspiciously high win rate with significant sample size"
                )

        return warnings, anomalies
