"""Client for Polymarket Data API - fetches wallet activity and history."""

from dataclasses import dataclass
from datetime import datetime

import httpx


@dataclass
class WalletActivity:
    """Represents a single activity record for a wallet."""

    timestamp: datetime
    transaction_hash: str
    activity_type: str  # TRADE, SPLIT, MERGE, REDEEM, REWARD, CONVERSION
    size: float
    usd_size: float
    market_id: str | None
    market_title: str | None
    side: str | None  # BUY or SELL
    price: float | None


@dataclass
class WalletSummary:
    """Summary of a wallet's trading history."""

    address: str
    total_trades: int
    first_trade_at: datetime | None
    activities: list[WalletActivity]


@dataclass
class Position:
    """A user's position in a market."""

    market_id: str
    market_title: str
    market_slug: str
    outcome: str
    size: float
    avg_price: float
    initial_value: float
    current_value: float
    cash_pnl: float
    percent_pnl: float
    realized_pnl: float
    current_price: float
    redeemable: bool


@dataclass
class PortfolioSummary:
    """Aggregate portfolio stats from positions endpoint."""

    address: str
    position_count: int
    total_value: float
    total_initial_value: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[Position]


class DataApiClient:
    """Client for Polymarket Data API."""

    def __init__(self, base_url: str = "https://data-api.polymarket.com"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def get_wallet_activity(
        self,
        address: str,
        limit: int = 500,
        activity_type: str | None = "TRADE",
    ) -> WalletSummary:
        """
        Fetch activity history for a wallet address.

        Args:
            address: Wallet address (0x-prefixed)
            limit: Maximum number of records to fetch (max 500)
            activity_type: Filter by type (TRADE, SPLIT, MERGE, etc.)

        Returns:
            WalletSummary with activity records
        """
        params = {
            "user": address,
            "limit": min(limit, 500),
            "sortBy": "TIMESTAMP",
            "sortDirection": "ASC",  # Get oldest first to find first trade
        }

        if activity_type:
            params["type"] = activity_type

        response = await self._client.get(
            f"{self.base_url}/activity",
            params=params,
        )
        response.raise_for_status()

        data = response.json()

        activities = []
        for item in data:
            ts = item.get("timestamp")
            if not ts:
                continue
            # Handle both Unix timestamp (int) and ISO string
            if isinstance(ts, (int, float)):
                timestamp = datetime.fromtimestamp(ts)
            else:
                timestamp = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

            activity = WalletActivity(
                timestamp=timestamp,
                transaction_hash=item.get("transactionHash", ""),
                activity_type=item.get("type", "UNKNOWN"),
                size=float(item.get("size", 0)),
                usd_size=float(item.get("usdcSize", 0)),
                market_id=item.get("conditionId"),
                market_title=item.get("title"),
                side=item.get("side"),
                price=float(item["price"]) if item.get("price") else None,
            )
            activities.append(activity)

        # Count only TRADE activities for trade count
        trade_activities = [a for a in activities if a.activity_type == "TRADE"]
        first_trade = trade_activities[0] if trade_activities else None

        return WalletSummary(
            address=address,
            total_trades=len(trade_activities),
            first_trade_at=first_trade.timestamp if first_trade else None,
            activities=activities,
        )

    async def get_trade_count(self, address: str) -> int:
        """
        Get the total number of trades for a wallet.

        This is a convenience method that fetches activity and counts trades.
        """
        summary = await self.get_wallet_activity(
            address, limit=500, activity_type="TRADE"
        )
        return summary.total_trades

    async def get_portfolio_value(self, address: str) -> float:
        """
        Get total USD value of a user's positions.

        Args:
            address: Wallet address

        Returns:
            Total portfolio value in USD
        """
        response = await self._client.get(
            f"{self.base_url}/value",
            params={"user": address},
        )
        response.raise_for_status()

        data = response.json()
        if data and len(data) > 0:
            return float(data[0].get("value", 0))
        return 0.0

    async def get_positions(self, address: str, limit: int = 500) -> list[Position]:
        """
        Get all positions for a wallet with P&L data.

        Args:
            address: Wallet address
            limit: Maximum positions to fetch

        Returns:
            List of Position objects
        """
        response = await self._client.get(
            f"{self.base_url}/positions",
            params={"user": address, "limit": limit},
        )
        response.raise_for_status()

        data = response.json()
        positions = []

        for item in data:
            position = Position(
                market_id=item.get("conditionId", ""),
                market_title=item.get("title", "Unknown"),
                market_slug=item.get("slug", ""),
                outcome=item.get("outcome", ""),
                size=float(item.get("size", 0)),
                avg_price=float(item.get("avgPrice", 0)),
                initial_value=float(item.get("initialValue", 0)),
                current_value=float(item.get("currentValue", 0)),
                cash_pnl=float(item.get("cashPnl", 0)),
                percent_pnl=float(item.get("percentPnl", 0)),
                realized_pnl=float(item.get("realizedPnl", 0)),
                current_price=float(item.get("curPrice", 0)),
                redeemable=item.get("redeemable", False),
            )
            positions.append(position)

        return positions

    async def get_portfolio_summary(self, address: str) -> PortfolioSummary:
        """
        Get aggregate portfolio stats by summing all positions.

        This is much faster than fetching all individual trades.

        Args:
            address: Wallet address

        Returns:
            PortfolioSummary with aggregate stats
        """
        positions = await self.get_positions(address)

        total_value = sum(p.current_value for p in positions)
        total_initial = sum(p.initial_value for p in positions)
        unrealized_pnl = sum(p.cash_pnl for p in positions)
        realized_pnl = sum(p.realized_pnl for p in positions)

        return PortfolioSummary(
            address=address,
            position_count=len(positions),
            total_value=total_value,
            total_initial_value=total_initial,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            positions=positions,
        )
