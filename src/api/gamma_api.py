"""Client for Polymarket Gamma API - fetches market metadata."""

from dataclasses import dataclass

import httpx


@dataclass
class Market:
    """Represents a Polymarket market."""

    id: str  # condition_id
    question: str
    slug: str
    volume: float
    liquidity: float
    active: bool
    closed: bool
    outcomes: list[str]


@dataclass
class Event:
    """Represents a Polymarket event (can contain multiple markets)."""

    id: str
    title: str
    slug: str
    markets: list[Market]


class GammaApiClient:
    """Client for Polymarket Gamma API."""

    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)
        self._market_cache: dict[str, Market] = {}

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def get_market(self, condition_id: str) -> Market | None:
        """
        Fetch a single market by its condition ID.

        Args:
            condition_id: The market's condition ID

        Returns:
            Market object or None if not found
        """
        # Check cache first
        if condition_id in self._market_cache:
            return self._market_cache[condition_id]

        try:
            response = await self._client.get(
                f"{self.base_url}/markets",
                params={"id": condition_id},
            )
            response.raise_for_status()

            data = response.json()
            if not data:
                return None

            market_data = data[0] if isinstance(data, list) else data

            market = Market(
                id=market_data.get("conditionId", condition_id),
                question=market_data.get("question", "Unknown"),
                slug=market_data.get("slug", ""),
                volume=float(market_data.get("volume", 0)),
                liquidity=float(market_data.get("liquidity", 0)),
                active=market_data.get("active", False),
                closed=market_data.get("closed", False),
                outcomes=market_data.get("outcomes", ["Yes", "No"]),
            )

            self._market_cache[condition_id] = market
            return market

        except httpx.HTTPStatusError:
            return None

    async def get_market_name(self, condition_id: str) -> str:
        """
        Get the human-readable name/question for a market.

        Args:
            condition_id: The market's condition ID

        Returns:
            Market question or "Unknown Market" if not found
        """
        market = await self.get_market(condition_id)
        return market.question if market else "Unknown Market"

    async def get_active_markets(self, limit: int = 100) -> list[Market]:
        """
        Fetch active markets.

        Args:
            limit: Maximum number of markets to fetch

        Returns:
            List of active Market objects
        """
        response = await self._client.get(
            f"{self.base_url}/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
            },
        )
        response.raise_for_status()

        data = response.json()
        markets = []

        for market_data in data:
            market = Market(
                id=market_data.get("conditionId", ""),
                question=market_data.get("question", "Unknown"),
                slug=market_data.get("slug", ""),
                volume=float(market_data.get("volume", 0)),
                liquidity=float(market_data.get("liquidity", 0)),
                active=market_data.get("active", False),
                closed=market_data.get("closed", False),
                outcomes=market_data.get("outcomes", ["Yes", "No"]),
            )
            markets.append(market)
            self._market_cache[market.id] = market

        return markets
