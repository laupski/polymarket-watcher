"""
Test harness for anomaly detection against known accounts.

This module tests the detection rules against real Polymarket accounts
to verify they correctly identify anomalous behavior patterns.
"""

import asyncio
from dataclasses import dataclass

import httpx


@dataclass
class TestAccount:
    """A test account with expected detection results."""

    address: str
    username: str | None
    description: str
    should_trigger_low_history: bool
    should_trigger_concentrated: bool


# Known anomaly accounts for testing
TEST_ACCOUNTS = [
    TestAccount(
        address="0x31a56e9E690c621eD21De08Cb559e9524Cdb8eD9",
        username=None,
        description="Venezuela-focused bettor: ~$40k volume, 15 trades, all on Maduro/invasion markets",
        should_trigger_low_history=True,  # Has $7k trades, <20 trade history
        should_trigger_concentrated=True,  # High volume, few trades, concentrated
    ),
    TestAccount(
        address="0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d",
        username="gabagool22",
        description="Active trader with many trades - should NOT trigger",
        should_trigger_low_history=False,  # Has thousands of trades
        should_trigger_concentrated=False,  # Too many trades
    ),
]


async def get_wallet_stats(address: str) -> dict:
    """Fetch wallet statistics from the API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://data-api.polymarket.com/activity",
            params={"user": address, "limit": 500, "type": "TRADE"},
        )
        resp.raise_for_status()
        trades = resp.json()

        if not trades:
            return {
                "trade_count": 0,
                "total_volume": 0,
                "max_trade": 0,
                "avg_trade": 0,
            }

        total_volume = sum(float(t.get("usdcSize", 0)) for t in trades)
        max_trade = max(float(t.get("usdcSize", 0)) for t in trades)

        return {
            "trade_count": len(trades),
            "total_volume": total_volume,
            "max_trade": max_trade,
            "avg_trade": total_volume / len(trades) if trades else 0,
        }


def check_low_history_detection(
    stats: dict,
    large_trade_usd: float = 5000,
    low_history_threshold: int = 20,
) -> bool:
    """Check if account would trigger low history detector."""
    return (
        stats["max_trade"] >= large_trade_usd
        and stats["trade_count"] < low_history_threshold
    )


def check_concentrated_detection(
    stats: dict,
    min_volume_usd: float = 10000,
    max_trades: int = 25,
    min_avg_trade: float = 1000,
) -> bool:
    """Check if account would trigger concentrated betting detector."""
    return (
        stats["total_volume"] >= min_volume_usd
        and stats["trade_count"] <= max_trades
        and stats["avg_trade"] >= min_avg_trade
    )


async def test_account(account: TestAccount) -> tuple[bool, str]:
    """
    Test a single account against detection rules.

    Returns:
        (passed, message) tuple
    """
    try:
        stats = await get_wallet_stats(account.address)
    except Exception as e:
        return False, f"Failed to fetch stats: {e}"

    low_history_triggered = check_low_history_detection(stats)
    concentrated_triggered = check_concentrated_detection(stats)

    errors = []

    if low_history_triggered != account.should_trigger_low_history:
        expected = "trigger" if account.should_trigger_low_history else "NOT trigger"
        actual = "triggered" if low_history_triggered else "did NOT trigger"
        errors.append(f"Low history detector should {expected} but {actual}")

    if concentrated_triggered != account.should_trigger_concentrated:
        expected = "trigger" if account.should_trigger_concentrated else "NOT trigger"
        actual = "triggered" if concentrated_triggered else "did NOT trigger"
        errors.append(f"Concentrated detector should {expected} but {actual}")

    if errors:
        details = (
            f"Stats: {stats['trade_count']} trades, "
            f"${stats['total_volume']:,.2f} volume, "
            f"max ${stats['max_trade']:,.2f}, "
            f"avg ${stats['avg_trade']:,.2f}"
        )
        return False, f"{'; '.join(errors)} | {details}"

    return True, "All checks passed"


async def run_all_tests() -> None:
    """Run all anomaly detection tests."""
    print("=" * 80)
    print("ANOMALY DETECTION TEST HARNESS")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for account in TEST_ACCOUNTS:
        name = account.username or account.address[:12] + "..."
        print(f"Testing: {name}")
        print(f"  Description: {account.description}")

        success, message = await test_account(account)

        if success:
            print(f"  Result: \033[92mPASS\033[0m - {message}")
            passed += 1
        else:
            print(f"  Result: \033[91mFAIL\033[0m - {message}")
            failed += 1

        print()

    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed > 0:
        exit(1)


def main():
    """CLI entry point."""
    asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
