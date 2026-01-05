"""CLI tool to analyze Polymarket wallet profitability."""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone

import httpx

from .analysis.dashboard import (
    print_analysis,
    print_comparison,
    print_portfolio_summary,
)
from .analysis.profitability import ProfitabilityAnalyzer
from .api.data_api import DataApiClient

# Known wallet mappings (username -> address)
KNOWN_WALLETS = {
    "gabagool22": "0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d",
    "distinct-baguette": "0xe00740bce98a594e26861838885ab310ec3b548c",
    "Account88888": "0x7f69983eb28245bba0d5083502a78744a8f66162",
}


async def resolve_wallet(identifier: str) -> tuple[str, str | None]:
    """
    Resolve a wallet identifier to an address.

    Accepts:
    - 0x... address
    - @username
    - https://polymarket.com/@username URL

    Returns:
        (address, username) tuple
    """
    # Already an address
    if identifier.startswith("0x") and len(identifier) == 42:
        return identifier.lower(), None

    # Extract username from URL or @mention
    username = None
    if "polymarket.com/@" in identifier:
        match = re.search(r"polymarket\.com/@([\w-]+)", identifier)
        if match:
            username = match.group(1)
    elif identifier.startswith("@"):
        username = identifier[1:]
    else:
        username = identifier

    if not username:
        raise ValueError(f"Could not parse identifier: {identifier}")

    # Check known wallets first
    if username in KNOWN_WALLETS:
        return KNOWN_WALLETS[username], username

    # Try to fetch from Polymarket API
    async with httpx.AsyncClient() as client:
        try:
            # Try the profiles API
            response = await client.get(
                f"https://polymarket.com/api/profile/{username}",
                follow_redirects=True,
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                if "proxyWallet" in data:
                    return data["proxyWallet"].lower(), username
                if "address" in data:
                    return data["address"].lower(), username
        except Exception as e:
            logging.debug(f"Could not fetch profile for {username}: {e}")

    raise ValueError(f"Could not resolve wallet address for: {username}")


async def main_async(args):
    """Async main function."""
    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Resolve wallet addresses
    wallets = []
    for identifier in args.wallets:
        try:
            address, username = await resolve_wallet(identifier)
            wallets.append((address, username))
            logging.info(
                f"Resolved {identifier} -> {address[:10]}... ({username or 'no username'})"
            )
        except ValueError as e:
            logging.error(str(e))
            sys.exit(1)

    # Quick mode uses positions endpoint for fast aggregate stats
    if args.quick:
        data_client = DataApiClient()
        try:
            for address, username in wallets:
                print(
                    f"\nFetching portfolio summary for {username or address[:10]}...",
                    flush=True,
                )
                summary = await data_client.get_portfolio_summary(address)
                print_portfolio_summary(summary, username)
        finally:
            await data_client.close()
        return

    # Full analysis mode - fetches individual trades
    analyzer = ProfitabilityAnalyzer()

    # Calculate timestamp for --today filter
    start_timestamp = None
    if args.today:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_timestamp = int(today_start.timestamp())
        print(f"Filtering trades from today ({today_start.strftime('%Y-%m-%d')} UTC)")

    try:
        analyses = []

        for address, username in wallets:
            print(f"\nAnalyzing {username or address[:10]}...", flush=True)
            analysis = await analyzer.analyze_wallet(
                address,
                username,
                max_trades=args.max_trades,
                start_timestamp=start_timestamp,
            )
            analyses.append(analysis)

            if not args.compare:
                print_analysis(analysis)

        if args.compare and len(analyses) > 1:
            print_comparison(analyses)

            # Also print individual analyses if verbose
            if args.verbose:
                for analysis in analyses:
                    print_analysis(analysis)

    finally:
        await analyzer.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Polymarket wallet profitability and trading strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a single wallet by address
  python -m src.analyze 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d

  # Analyze by username
  python -m src.analyze @gabagool22

  # Analyze by Polymarket URL
  python -m src.analyze https://polymarket.com/@gabagool22

  # Quick portfolio summary (fast, uses positions endpoint)
  python -m src.analyze @gabagool22 --quick

  # Compare multiple wallets
  python -m src.analyze @gabagool22 @distinct-baguette @Account88888 --compare

  # Verbose output with debug logging
  python -m src.analyze @gabagool22 --verbose --debug
        """,
    )

    parser.add_argument(
        "wallets",
        nargs="+",
        help="Wallet addresses, @usernames, or Polymarket profile URLs to analyze",
    )

    parser.add_argument(
        "--compare",
        "-c",
        action="store_true",
        help="Show comparison table for multiple wallets",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for each wallet when comparing",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--max-trades",
        "-m",
        type=int,
        default=50000,
        help="Maximum trades to fetch per wallet (default: 50000)",
    )

    parser.add_argument(
        "--today",
        "-t",
        action="store_true",
        help="Only analyze trades from today",
    )

    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Quick mode: show portfolio summary using positions endpoint (much faster)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nAnalysis interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
