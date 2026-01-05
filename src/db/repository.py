"""Database repository for wallet cache, alerts, and trades."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite

from .models import SCHEMA

logger = logging.getLogger(__name__)


@dataclass
class CachedWallet:
    """Cached wallet information."""

    address: str
    trade_count: int
    first_trade_at: datetime | None
    last_updated: datetime


@dataclass
class Alert:
    """An anomaly alert record."""

    id: int | None
    created_at: datetime
    alert_type: str
    wallet_address: str
    trade_size_usd: float
    wallet_trade_count: int | None
    market_id: str | None
    market_name: str | None
    outcome: str | None
    side: str | None
    transaction_hash: str | None
    details: dict | None


class Repository:
    """Database repository for all persistence operations."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self):
        """Initialize the database and create tables."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Create tables
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

        logger.info(f"Database initialized at {self.db_path}")

    async def close(self):
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._connection

    # Wallet Cache Operations

    async def get_cached_wallet(self, address: str) -> CachedWallet | None:
        """Get cached wallet info if available."""
        async with self.conn.execute(
            "SELECT * FROM wallet_cache WHERE address = ?", (address.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            return CachedWallet(
                address=row["address"],
                trade_count=row["trade_count"],
                first_trade_at=datetime.fromisoformat(row["first_trade_at"])
                if row["first_trade_at"]
                else None,
                last_updated=datetime.fromisoformat(row["last_updated"]),
            )

    async def get_cached_wallet_if_fresh(
        self,
        address: str,
        max_age_hours: int = 24,
    ) -> CachedWallet | None:
        """Get cached wallet info if it's still fresh."""
        cached = await self.get_cached_wallet(address)
        if not cached:
            return None

        age = datetime.now() - cached.last_updated
        if age > timedelta(hours=max_age_hours):
            return None

        return cached

    async def cache_wallet(
        self,
        address: str,
        trade_count: int,
        first_trade_at: datetime | None = None,
    ):
        """Cache wallet trade count."""
        await self.conn.execute(
            """
            INSERT INTO wallet_cache (address, trade_count, first_trade_at, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                trade_count = excluded.trade_count,
                first_trade_at = COALESCE(excluded.first_trade_at, wallet_cache.first_trade_at),
                last_updated = excluded.last_updated
            """,
            (
                address.lower(),
                trade_count,
                first_trade_at.isoformat() if first_trade_at else None,
                datetime.now().isoformat(),
            ),
        )
        await self.conn.commit()

    async def increment_wallet_trade_count(self, address: str):
        """Increment the cached trade count for a wallet."""
        await self.conn.execute(
            """
            UPDATE wallet_cache
            SET trade_count = trade_count + 1, last_updated = ?
            WHERE address = ?
            """,
            (datetime.now().isoformat(), address.lower()),
        )
        await self.conn.commit()

    # Alert Operations

    async def save_alert(self, alert: Alert) -> int:
        """Save an alert and return its ID."""
        async with self.conn.execute(
            """
            INSERT INTO alerts (
                created_at, alert_type, wallet_address, trade_size_usd,
                wallet_trade_count, market_id, market_name, outcome, side,
                transaction_hash, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.created_at.isoformat(),
                alert.alert_type,
                alert.wallet_address.lower(),
                alert.trade_size_usd,
                alert.wallet_trade_count,
                alert.market_id,
                alert.market_name,
                alert.outcome,
                alert.side,
                alert.transaction_hash,
                json.dumps(alert.details) if alert.details else None,
            ),
        ) as cursor:
            alert_id = cursor.lastrowid

        await self.conn.commit()
        return alert_id or 0

    async def get_recent_alerts(self, limit: int = 100) -> list[Alert]:
        """Get recent alerts."""
        async with self.conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()

            return [
                Alert(
                    id=row["id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    alert_type=row["alert_type"],
                    wallet_address=row["wallet_address"],
                    trade_size_usd=row["trade_size_usd"],
                    wallet_trade_count=row["wallet_trade_count"],
                    market_id=row["market_id"],
                    market_name=row["market_name"],
                    outcome=row["outcome"],
                    side=row["side"],
                    transaction_hash=row["transaction_hash"],
                    details=json.loads(row["details"]) if row["details"] else None,
                )
                for row in rows
            ]

    # Trade Operations

    async def save_trade(
        self,
        transaction_hash: str,
        wallet_address: str,
        market_id: str | None,
        market_slug: str | None,
        outcome: str | None,
        side: str | None,
        size: float,
        price: float,
        usd_value: float,
        timestamp: datetime,
    ):
        """Save a trade record."""
        try:
            await self.conn.execute(
                """
                INSERT OR IGNORE INTO trades (
                    transaction_hash, wallet_address, market_id, market_slug,
                    outcome, side, size, price, usd_value, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_hash,
                    wallet_address.lower(),
                    market_id,
                    market_slug,
                    outcome,
                    side,
                    size,
                    price,
                    usd_value,
                    timestamp.isoformat(),
                ),
            )
            await self.conn.commit()
        except Exception as e:
            logger.debug(f"Error saving trade (likely duplicate): {e}")

    async def get_wallet_trade_count_from_db(self, address: str) -> int:
        """Count trades for a wallet from our local trade history."""
        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM trades WHERE wallet_address = ?",
            (address.lower(),),
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0
