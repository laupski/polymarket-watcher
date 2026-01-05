"""Console dashboard for displaying wallet analysis results."""

from datetime import datetime

from ..api.data_api import PortfolioSummary, Position
from .profitability import StrategyInsights, TradeAnalysis, WalletProfile


def format_currency(value: float) -> str:
    """Format a number as currency."""
    if value >= 0:
        return f"${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_large_number(value: float) -> str:
    """Format large numbers with K/M suffixes."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def create_bar(value: float, max_value: float, width: int = 20) -> str:
    """Create a simple ASCII progress bar."""
    if max_value <= 0:
        return " " * width
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def print_header(title: str, width: int = 80):
    """Print a section header."""
    print()
    print("═" * width)
    print(f"  {title}")
    print("═" * width)


def print_subheader(title: str, width: int = 80):
    """Print a subsection header."""
    print()
    print(f"─── {title} " + "─" * (width - len(title) - 5))


def print_analysis(analysis: TradeAnalysis):
    """Print the full analysis dashboard."""
    profile = analysis.profile
    strategy = profile.strategy

    # Main header
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " POLYMARKET WALLET ANALYSIS ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    # Wallet info
    print_header("WALLET PROFILE")
    print(f"  Address:    {profile.address}")
    if profile.username:
        print(f"  Username:   @{profile.username}")
    if profile.first_trade_at:
        print(f"  First Trade: {profile.first_trade_at.strftime('%Y-%m-%d')}")
        print(
            f"  Last Trade:  {profile.last_trade_at.strftime('%Y-%m-%d') if profile.last_trade_at else 'N/A'}"
        )
    print(f"  Active Days: {profile.active_days}")

    # Performance overview
    print_header("PERFORMANCE OVERVIEW")

    pnl_color = "\033[92m" if profile.total_pnl >= 0 else "\033[91m"
    reset = "\033[0m"

    print(f"""
  ┌────────────────────────┬────────────────────────┬────────────────────────┐
  │   TOTAL P&L            │   TOTAL VOLUME         │   TOTAL TRADES         │
  │   {pnl_color}{format_currency(profile.total_pnl):>18}{reset}   │   {format_large_number(profile.total_volume):>18}   │   {profile.total_trades:>18,}   │
  └────────────────────────┴────────────────────────┴────────────────────────┘
    """)

    # Key metrics
    roi = (
        (profile.total_pnl / profile.total_volume * 100)
        if profile.total_volume > 0
        else 0
    )

    print("  Key Metrics:")
    print(
        f"    Win Rate:        {profile.win_rate * 100:>6.1f}%  {create_bar(profile.win_rate, 1.0, 15)}"
    )
    print(
        f"    Profit Factor:   {profile.profit_factor:>6.2f}x {'(excellent)' if profile.profit_factor > 2 else '(good)' if profile.profit_factor > 1.5 else ''}"
    )
    print(f"    ROI:             {roi:>6.2f}%")
    print(f"    Avg P&L/Trade:   {format_currency(profile.avg_profit_per_trade):>10}")
    print(f"    Best Trade:      {format_currency(profile.best_trade_pnl):>10}")
    print(f"    Worst Trade:     {format_currency(profile.worst_trade_pnl):>10}")
    if profile.sharpe_ratio:
        print(f"    Sharpe Ratio:    {profile.sharpe_ratio:>6.2f}")

    # Strategy analysis
    if strategy:
        print_header("STRATEGY ANALYSIS")

        print(f"""
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  Primary Strategy: {strategy.primary_strategy:<40} Confidence: {strategy.confidence * 100:.0f}%  │
  └─────────────────────────────────────────────────────────────────────────────┘
        """)

        print("  Characteristics:")
        for char in strategy.characteristics:
            print(f"    • {char}")

        print_subheader("Trading Patterns")
        print(f"    Trades/Day:      {strategy.trades_per_day:>8.1f}")
        print(
            f"    Avg Trade Size:  {format_currency(strategy.avg_trade_size_usd):>10}"
        )
        print(
            f"    Median Trade:    {format_currency(strategy.median_trade_size_usd):>10}"
        )
        print(f"    Max Position:    {format_currency(strategy.max_position_usd):>10}")
        if strategy.avg_hold_time_hours:
            if strategy.avg_hold_time_hours < 1:
                print(
                    f"    Avg Hold Time:   {strategy.avg_hold_time_hours * 60:>6.0f} minutes"
                )
            elif strategy.avg_hold_time_hours < 24:
                print(
                    f"    Avg Hold Time:   {strategy.avg_hold_time_hours:>6.1f} hours"
                )
            else:
                print(
                    f"    Avg Hold Time:   {strategy.avg_hold_time_hours / 24:>6.1f} days"
                )

        print_subheader("Market Preferences")
        if strategy.favorite_categories:
            total = sum(c for _, c in strategy.favorite_categories)
            for cat, count in strategy.favorite_categories[:4]:
                pct = count / total * 100
                bar = create_bar(count, total, 15)
                print(f"    {cat:<12} {bar} {pct:>5.1f}% ({count:,} trades)")

        print()
        if strategy.prefers_favorites:
            print("    Price Target: Prefers FAVORITES (high probability outcomes)")
        elif strategy.prefers_underdogs:
            print("    Price Target: Prefers UNDERDOGS (low probability outcomes)")
        else:
            print("    Price Target: Balanced (no strong preference)")

        print_subheader("Timing Analysis")
        print(
            f"    Most Active Hours (UTC): {', '.join(f'{h:02d}:00' for h in strategy.most_active_hours)}"
        )
        print(f"    Weekend Trader: {'Yes' if strategy.weekend_trader else 'No'}")
        print(
            f"    Position Sizing: {'Consistent' if strategy.position_sizing_consistent else 'Variable'}"
        )

    # Top positions
    if profile.positions:
        print_header("TOP POSITIONS (by P&L)")
        print()
        print(
            "    Market                                           Side     P&L        Trades"
        )
        print("    " + "─" * 72)

        for i, pos in enumerate(profile.positions[:10]):
            market_name = (
                pos.market_title[:40] + "..."
                if len(pos.market_title) > 40
                else pos.market_title
            )
            pnl_str = format_currency(pos.realized_pnl)
            if pos.realized_pnl >= 0:
                pnl_str = f"\033[92m{pnl_str}\033[0m"
            else:
                pnl_str = f"\033[91m{pnl_str}\033[0m"

            net = (
                "LONG"
                if pos.net_position > 0
                else "SHORT"
                if pos.net_position < 0
                else "FLAT"
            )
            print(f"    {market_name:<45} {net:<6} {pnl_str:>15}  {pos.trade_count:>5}")

    # Anomalies and warnings
    if analysis.anomalies or analysis.warnings:
        print_header("ALERTS & ANOMALIES")

        if analysis.anomalies:
            print()
            print("  🚨 ANOMALIES DETECTED:")
            for anomaly in analysis.anomalies:
                print(f"     ⚠️  {anomaly}")

        if analysis.warnings:
            print()
            print("  ⚡ WARNINGS:")
            for warning in analysis.warnings:
                print(f"     •  {warning}")

    # Footer
    print()
    print("─" * 80)
    print(f"  Analysis generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 80)
    print()


def print_portfolio_summary(
    summary: PortfolioSummary, username: str | None = None, show_positions: bool = True
):
    """Print a quick portfolio summary using the positions endpoint."""
    total_pnl = summary.unrealized_pnl + summary.realized_pnl

    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " OPEN POSITIONS SUMMARY ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    # Wallet info
    print()
    print(f"  Address:    {summary.address}")
    if username:
        print(f"  Username:   @{username}")

    # Warning about limitations
    print()
    print(
        "  \033[93mNOTE: This only shows OPEN positions. Closed/settled markets are excluded.\033[0m"
    )
    print("  \033[93mFor accurate all-time P&L, run without --quick flag.\033[0m")

    # Performance overview
    pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
    reset = "\033[0m"

    print(f"""
  ┌────────────────────────┬────────────────────────┬────────────────────────┐
  │   OPEN P&L             │   UNREALIZED           │   REALIZED (partial)   │
  │   {pnl_color}{format_currency(total_pnl):>18}{reset}   │   {format_currency(summary.unrealized_pnl):>18}   │   {format_currency(summary.realized_pnl):>18}   │
  └────────────────────────┴────────────────────────┴────────────────────────┘
    """)

    print(f"  Open Positions:  {summary.position_count:>10}")
    print(f"  Current Value:   {format_currency(summary.total_value):>10}")
    print(f"  Initial Value:   {format_currency(summary.total_initial_value):>10}")

    # Top positions by P&L
    if show_positions and summary.positions:
        # Sort by total P&L (unrealized + realized)
        sorted_positions = sorted(
            summary.positions, key=lambda p: p.cash_pnl + p.realized_pnl, reverse=True
        )

        print()
        print("─── Top Positions by P&L " + "─" * 53)
        print()
        print(
            "    Market                                       Outcome   Value      P&L"
        )
        print("    " + "─" * 72)

        for pos in sorted_positions[:10]:
            market_name = (
                pos.market_title[:38] + "..."
                if len(pos.market_title) > 38
                else pos.market_title
            )
            total_pos_pnl = pos.cash_pnl + pos.realized_pnl
            pnl_str = format_currency(total_pos_pnl)
            if total_pos_pnl >= 0:
                pnl_str = f"\033[92m{pnl_str}\033[0m"
            else:
                pnl_str = f"\033[91m{pnl_str}\033[0m"

            outcome_str = pos.outcome[:6] if pos.outcome else "?"
            print(
                f"    {market_name:<42} {outcome_str:<8} {format_currency(pos.current_value):>10} {pnl_str:>15}"
            )

    # Footer
    print()
    print("─" * 80)
    print(f"  Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 80)
    print()


def print_comparison(analyses: list[TradeAnalysis]):
    """Print a comparison table of multiple wallets."""
    if not analyses:
        return

    print()
    print("╔" + "═" * 98 + "╗")
    print("║" + " WALLET COMPARISON ".center(98) + "║")
    print("╚" + "═" * 98 + "╝")
    print()

    # Header row
    print(
        f"  {'Wallet':<20} {'P&L':>14} {'Volume':>14} {'Win Rate':>10} {'ROI':>8} {'Trades':>10} {'Strategy':<20}"
    )
    print("  " + "─" * 96)

    for analysis in analyses:
        p = analysis.profile
        s = p.strategy

        username = f"@{p.username}" if p.username else p.address[:12] + "..."
        roi = (p.total_pnl / p.total_volume * 100) if p.total_volume > 0 else 0
        strategy = s.primary_strategy[:18] if s else "Unknown"

        pnl_str = format_large_number(p.total_pnl)
        if p.total_pnl >= 0:
            pnl_str = f"\033[92m{pnl_str}\033[0m"
        else:
            pnl_str = f"\033[91m{pnl_str}\033[0m"

        print(
            f"  {username:<20} {pnl_str:>14} {format_large_number(p.total_volume):>14} {p.win_rate * 100:>9.1f}% {roi:>7.2f}% {p.total_trades:>10,} {strategy:<20}"
        )

    print()

    # Anomaly summary
    any_anomalies = any(a.anomalies for a in analyses)
    if any_anomalies:
        print("  ANOMALY SUMMARY:")
        for analysis in analyses:
            if analysis.anomalies:
                username = (
                    f"@{analysis.profile.username}"
                    if analysis.profile.username
                    else analysis.profile.address[:12]
                )
                print(f"    {username}:")
                for anomaly in analysis.anomalies:
                    print(f"      • {anomaly}")
        print()
