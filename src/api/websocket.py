"""WebSocket client for Polymarket Real-Time Data Socket (RTDS)."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a trade from the RTDS WebSocket."""

    asset: str  # ERC1155 token ID
    condition_id: str  # Market condition ID
    price: float
    side: str  # BUY or SELL
    size: float
    timestamp: datetime
    outcome: str  # Human readable outcome
    slug: str  # Market slug
    event_slug: str
    transaction_hash: str
    # User info
    proxy_wallet: str  # Trader's proxy wallet address
    pseudonym: str | None = None

    @property
    def usd_value(self) -> float:
        """Calculate USD value of the trade."""
        return self.size * self.price


TradeCallback = Callable[[Trade], Awaitable[None]]


class RtdsWebSocketClient:
    """Client for Polymarket Real-Time Data Socket."""

    WEBSOCKET_URL = "wss://ws-live-data.polymarket.com"
    PING_INTERVAL = 5  # seconds
    RECONNECT_DELAY = 5  # seconds

    def __init__(
        self,
        on_trade: TradeCallback | None = None,
        on_connect: Callable[[], Awaitable[None]] | None = None,
        on_disconnect: Callable[[], Awaitable[None]] | None = None,
    ):
        self.on_trade = on_trade
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self._ws: ClientConnection | None = None
        self._running = False
        self._ping_task: asyncio.Task | None = None

    async def connect(self):
        """Connect to the RTDS WebSocket and start listening."""
        self._running = True

        while self._running:
            try:
                logger.info(f"Connecting to {self.WEBSOCKET_URL}...")

                async with websockets.connect(
                    self.WEBSOCKET_URL,
                    ping_interval=None,  # We'll handle pings manually
                ) as ws:
                    self._ws = ws
                    logger.info("Connected to RTDS WebSocket")

                    if self.on_connect:
                        await self.on_connect()

                    # Subscribe to trades
                    await self._subscribe_to_trades()

                    # Start ping task
                    self._ping_task = asyncio.create_task(self._ping_loop())

                    # Listen for messages
                    await self._listen()

            except websockets.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                if self._ping_task:
                    self._ping_task.cancel()
                    try:
                        await self._ping_task
                    except asyncio.CancelledError:
                        pass

                if self.on_disconnect:
                    await self.on_disconnect()

                self._ws = None

            if self._running:
                logger.info(f"Reconnecting in {self.RECONNECT_DELAY} seconds...")
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def disconnect(self):
        """Disconnect from the WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _subscribe_to_trades(self):
        """Subscribe to trade messages."""
        if not self._ws:
            return

        subscribe_msg = {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": "activity",
                    "type": "trades",
                }
            ],
        }

        await self._ws.send(json.dumps(subscribe_msg))
        logger.info("Subscribed to trades")

    async def _ping_loop(self):
        """Send periodic pings to keep connection alive."""
        while self._running and self._ws:
            try:
                await asyncio.sleep(self.PING_INTERVAL)
                if self._ws:
                    await self._ws.ping()
            except Exception as e:
                logger.debug(f"Ping error: {e}")
                break

    async def _listen(self):
        """Listen for incoming messages."""
        if not self._ws:
            return

        async for message in self._ws:
            try:
                await self._handle_message(message)
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    async def _handle_message(self, raw_message: str):
        """Parse and handle an incoming message."""
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message: {raw_message[:100]}")
            return

        topic = data.get("topic")
        msg_type = data.get("type")

        # Handle trade messages
        if topic == "activity" and msg_type in ("trades", "orders_matched"):
            payload = data.get("payload", {})
            await self._handle_trade(payload)

    async def _handle_trade(self, payload: dict):
        """Process a trade payload."""
        if not self.on_trade:
            return

        try:
            # Parse timestamp - could be milliseconds or seconds
            ts = payload.get("timestamp", 0)
            if ts > 1e12:  # Milliseconds
                ts = ts / 1000

            trade = Trade(
                asset=payload.get("asset", ""),
                condition_id=payload.get("conditionId", ""),
                price=float(payload.get("price", 0)),
                side=payload.get("side", "UNKNOWN"),
                size=float(payload.get("size", 0)),
                timestamp=datetime.fromtimestamp(ts),
                outcome=payload.get("outcome", ""),
                slug=payload.get("slug", ""),
                event_slug=payload.get("eventSlug", ""),
                transaction_hash=payload.get("transactionHash", ""),
                proxy_wallet=payload.get("proxyWallet", ""),
                pseudonym=payload.get("pseudonym"),
            )

            await self.on_trade(trade)

        except Exception as e:
            logger.error(f"Error parsing trade: {e}, payload: {payload}")
