# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this codebase.

## Project Overview

Polymarket Watcher is a real-time anomaly detection system for Polymarket trades. It monitors the Polymarket WebSocket feed and flags suspicious trading patterns:
- Large trades from wallets with minimal trading history
- Wallets with suspiciously high win rates and profitability
- High-frequency trading bots

It also includes a wallet analyzer CLI tool to analyze any wallet's trading strategy.

## Tech Stack

- **Python 3.11+** with async/await
- **uv** for package management
- **websockets** for real-time data
- **httpx** for async HTTP requests
- **aiosqlite** for async SQLite
- **pyyaml** for configuration

## Commands

```bash
# Install dependencies
uv sync

# Run the real-time watcher
uv run python -m src.main

# Run with debug logging
uv run python -m src.main --debug

# Analyze a wallet's trading history
uv run python -m src.analyze @username

# Compare multiple wallets
uv run python -m src.analyze @wallet1 @wallet2 --compare

# Analyze with more historical trades
uv run python -m src.analyze @username --max-trades 10000
```

## Project Structure

```
src/
├── main.py                 # Entry point for real-time watcher
├── analyze.py              # CLI entry point for wallet analyzer
├── config.py               # Config dataclasses and YAML loader
├── api/
│   ├── websocket.py        # RTDS WebSocket client (real-time trades)
│   ├── data_api.py         # Data API client (wallet history)
│   └── gamma_api.py        # Gamma API client (market metadata)
├── db/
│   ├── models.py           # SQLite schema
│   └── repository.py       # Database operations
├── detection/
│   ├── engine.py           # Orchestrates all detectors
│   └── rules/
│       ├── low_history.py      # Low-history large trade detector
│       └── profitable_trader.py # Suspicious profitability detector
├── analysis/
│   ├── profitability.py    # Wallet analysis engine
│   └── dashboard.py        # Console dashboard formatting
└── alerting/
    └── logger.py           # Alert formatting and output
```

## Key Concepts

### Trade Flow (Real-time Watcher)
1. `RtdsWebSocketClient` connects to `wss://ws-live-data.polymarket.com`
2. Subscribes to `{"topic": "activity", "type": "trades"}`
3. Each trade is passed to `DetectionEngine.process_trade()`
4. Engine runs all registered detectors
5. Alerts are saved to DB and logged

### Detectors

**LowHistoryDetector** - Flags large trades from new wallets:
1. Is `trade.usd_value > config.large_trade_usd` (default $20,000)?
2. If yes, fetch wallet's trade count (cached or from API)
3. If `trade_count < config.low_history_threshold` (default 10), trigger alert

**ProfitableTraderDetector** - Tracks wallets over time and flags:
1. High win rates (>65%)
2. High profit factors (>2x)
3. High-frequency trading (>100 trades/day)
- Requires at least 2 suspicious patterns to trigger
- Tracks positions in-memory to estimate P&L

### Wallet Analyzer

The `src/analyze.py` CLI tool fetches a wallet's complete history and generates:
- Performance metrics (P&L, win rate, profit factor, Sharpe ratio)
- Strategy classification (scalping, swing trading, etc.)
- Market preferences (crypto, sports, politics)
- Timing patterns (active hours, hold times)
- Anomaly detection (suspicious patterns)

### Wallet Cache
To avoid hitting the Data API for every large trade:
- Wallet trade counts are cached in SQLite
- Cache expires after `config.cache_ttl_hours` (default 24)
- Cache is updated when we observe new trades

## Polymarket APIs

| API | Auth | Rate Limit | Used For |
|-----|------|------------|----------|
| RTDS WebSocket | None | N/A | Real-time trade stream |
| Data API `/activity` | None | ~1000/hr | Wallet trade history |
| Gamma API `/markets` | None | ~1000/hr | Market names |

All APIs are public - no authentication required.

## Adding a New Detector

1. Create `src/detection/rules/my_detector.py`:
```python
from dataclasses import dataclass
from src.api import Trade
from src.db import Alert, Repository

@dataclass
class MyDetectorConfig:
    threshold: float

class MyDetector:
    ALERT_TYPE = "my_detector_type"
    
    def __init__(self, config: MyDetectorConfig, repository: Repository, data_api):
        self.config = config
        self.repository = repository
        self.data_api = data_api
    
    async def analyze(self, trade: Trade) -> Alert | None:
        # Return Alert if anomaly detected, None otherwise
        if suspicious_condition:
            return Alert(
                id=None,
                created_at=datetime.now(),
                alert_type=self.ALERT_TYPE,
                wallet_address=trade.proxy_wallet,
                trade_size_usd=trade.usd_value,
                # ... other fields
            )
        return None
```

2. Add config to `src/config.py` DetectionConfig dataclass

3. Register in `src/main.py` in `PolymarketWatcher.start()`:
```python
my_config = MyDetectorConfig(threshold=self.config.detection.my_threshold)
my_detector = MyDetector(my_config, self.repository, self.data_api)
self.engine.add_detector(my_detector)
```

## Configuration

All settings are in `config.yaml`. Key values:

```yaml
detection:
  # Low History Detector
  large_trade_usd: 20000        # Min trade size to analyze
  low_history_threshold: 10     # Max trades for "low history"
  cache_ttl_hours: 24           # Wallet cache expiry
  
  # Profitable Trader Detector
  min_trades_for_analysis: 50   # Min trades before flagging
  min_profit_factor: 2.0        # Min win/loss ratio
  min_win_rate: 0.65            # Min win rate (65%)
  high_frequency_threshold: 100 # Trades/day for HFT flag
```

## Database

SQLite at `data/polymarket_watcher.db` with tables:
- `wallet_cache`: Cached trade counts per wallet
- `alerts`: All detected anomalies
- `trades`: All observed trades (for analysis)

## Common Tasks

### Analyze a profitable trader
```bash
uv run python -m src.analyze @gabagool22 --max-trades 10000
```

### Compare multiple wallets
```bash
uv run python -m src.analyze @wallet1 @wallet2 @wallet3 --compare
```

### Lower alert thresholds for testing
Edit `config.yaml`:
```yaml
detection:
  large_trade_usd: 1000
  min_trades_for_analysis: 20
  min_win_rate: 0.55
```

### View recent alerts
```bash
sqlite3 data/polymarket_watcher.db "SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;"
```

### Check trade volume
```bash
sqlite3 data/polymarket_watcher.db "SELECT COUNT(*) FROM trades;"
```

### Clear the database
```bash
rm data/polymarket_watcher.db
```

## Known Limitations

- No historical backfill - real-time watcher only monitors from when it starts
- Rate limited to ~1000 API calls/hour for wallet lookups
- WebSocket may disconnect; auto-reconnects after 5 seconds
- P&L calculation in real-time detector is estimated (based on observed trades only)
- Wallet analyzer fetches max 5000 trades by default (use `--max-trades` for more)

## Example Wallets for Testing

These are known profitable traders useful for testing the analyzer:
```bash
uv run python -m src.analyze @gabagool22 @distinct-baguette @Account88888 --compare
```
