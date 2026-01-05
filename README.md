# Polymarket Watcher

A real-time monitoring system that detects anomalous trading behavior on Polymarket. The primary use case is identifying large trades from wallets with minimal trading history, which could indicate insider trading, market manipulation, or other suspicious activity.

## Features

- **Real-time trade monitoring** via Polymarket WebSocket (RTDS)
- **Low-history detection** - flags large trades (>$5k) from wallets with few historical trades (<20)
- **Concentrated betting detection** - flags high-volume accounts with few trades focused on specific events
- **Profitable trader detection** - identifies wallets with suspicious win rates and trading patterns
- **Wallet profitability analyzer** - CLI tool to analyze any wallet's trading strategy
- **SQLite storage** - persists trades, wallet cache, and alerts for analysis
- **Configurable thresholds** - adjust detection parameters via YAML config
- **Test harness** - automated testing against known anomaly accounts
- **Extensible architecture** - easy to add new detection rules

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Clone the repository
git clone https://github.com/yourusername/polymarket-watcher.git
cd polymarket-watcher

# Install dependencies
uv sync
```

## Usage

```bash
# Run with default config
uv run python -m src.main

# Run with debug logging
uv run python -m src.main --debug

# Run with custom config file
uv run python -m src.main --config /path/to/config.yaml
```

### Wallet Analyzer

Analyze any wallet's trading history and strategy:

```bash
# Analyze a single wallet
uv run python -m src.analyze @gabagool22

# Analyze by wallet address
uv run python -m src.analyze 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d

# Compare multiple wallets
uv run python -m src.analyze @gabagool22 @distinct-baguette @Account88888 --compare

# Fetch more historical trades
uv run python -m src.analyze @gabagool22 --max-trades 10000

# Quick portfolio summary (open positions only, faster)
uv run python -m src.analyze @gabagool22 --quick
```

### Example Output

Normal operation (INFO level):
```
2024-01-15 14:30:00 | INFO | Starting Polymarket Watcher...
2024-01-15 14:30:01 | INFO | Database initialized at data/polymarket_watcher.db
2024-01-15 14:30:01 | INFO | Added detector: low_history_large_trade
2024-01-15 14:30:01 | INFO | Detection thresholds: large_trade=$20,000, low_history_threshold=10
2024-01-15 14:30:02 | INFO | Connected to Polymarket real-time data stream
2024-01-15 14:30:02 | INFO | Listening for trades...
```

When an anomaly is detected:
```
================================================================================
2024-01-15 14:32:17 | ALERT | LOW HISTORY LARGE TRADE
--------------------------------------------------------------------------------
  Wallet:      0x1234567890abcdef1234567890abcdef12345678
  Trade Size:  $45,230.00
  History:     3 previous trades
  Market:      will-bitcoin-reach-100k-by-march-2024
  Outcome:     Yes
  Side:        BUY
  Tx:          0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
================================================================================
```

## Configuration

Edit `config.yaml` to adjust detection parameters:

```yaml
detection:
  # Low History Detector
  large_trade_usd: 20000      # Minimum trade size (USD) to analyze
  low_history_threshold: 10   # Max trades to be considered "low history"
  cache_ttl_hours: 24         # How long to cache wallet history
  
  # Profitable Trader Detector
  min_trades_for_analysis: 50 # Min trades before analyzing a wallet
  min_profit_factor: 2.0      # Min win/loss ratio to flag
  min_win_rate: 0.65          # Min win rate to flag (65%)
  high_frequency_threshold: 100  # Trades/day for high-frequency flag

logging:
  level: INFO                 # DEBUG, INFO, WARNING, ERROR
  file: logs/alerts.log
  max_file_size_mb: 10
  backup_count: 5

api:
  data_api_base: "https://data-api.polymarket.com"
  gamma_api_base: "https://gamma-api.polymarket.com"
  websocket_url: "wss://ws-subscriptions-clob.polymarket.com/ws/market"
  requests_per_minute: 60

database:
  path: "data/polymarket_watcher.db"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Polymarket Watcher                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  WebSocket   │───>│  Detection   │───>│   Alerting   │   │
│  │   Client     │    │   Engine     │    │    Logger    │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                    │           │
│         v                   v                    v           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │    RTDS      │    │   SQLite     │    │  Console +   │   │
│  │  WebSocket   │    │   Database   │    │  Log File    │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Components

| Component | Location | Description |
|-----------|----------|-------------|
| WebSocket Client | `src/api/websocket.py` | Connects to Polymarket RTDS for real-time trades |
| Data API Client | `src/api/data_api.py` | Fetches wallet trading history |
| Gamma API Client | `src/api/gamma_api.py` | Fetches market metadata |
| Repository | `src/db/repository.py` | SQLite operations for cache, trades, alerts |
| Detection Engine | `src/detection/engine.py` | Orchestrates detection rules |
| Low History Detector | `src/detection/rules/low_history.py` | Flags low-history large trades |
| Profitable Trader Detector | `src/detection/rules/profitable_trader.py` | Flags suspicious win rates |
| Profitability Analyzer | `src/analysis/profitability.py` | Analyzes wallet trading strategies |
| Alert Logger | `src/alerting/logger.py` | Formats and outputs alerts |

## Polymarket APIs Used

| API | Endpoint | Authentication | Purpose |
|-----|----------|----------------|---------|
| RTDS WebSocket | `wss://ws-live-data.polymarket.com` | None (public) | Real-time trade stream |
| Data API | `https://data-api.polymarket.com/activity` | None (public) | Wallet trade history |
| Gamma API | `https://gamma-api.polymarket.com/markets` | None (public) | Market metadata |

No authentication is required - all data used is publicly available.

## Database Schema

The SQLite database contains three tables:

- **wallet_cache** - Caches wallet trade counts to minimize API calls
- **alerts** - Stores all detected anomalies
- **trades** - Stores all observed trades for historical analysis

## Adding New Detectors

Create a new detector in `src/detection/rules/`:

```python
from src.api import Trade
from src.db import Alert

class MyDetector:
    ALERT_TYPE = "my_detector"
    
    async def analyze(self, trade: Trade) -> Alert | None:
        # Your detection logic here
        if suspicious:
            return Alert(...)
        return None
```

Register it in `src/main.py`:

```python
my_detector = MyDetector(...)
self.engine.add_detector(my_detector)
```

## Future Enhancements

- [ ] Whale tracker - monitor known large wallets
- [ ] Volume spike detector - alert on sudden trading volume increases
- [ ] Coordination detector - identify multiple wallets trading in sync
- [ ] Discord/Slack webhook integration
- [ ] Web dashboard for viewing alerts
- [ ] Historical backtesting
- [ ] ML-based anomaly detection

## Changelog

### Unreleased

- **Concentrated Betting Detector** - flags accounts with high volume but few trades (e.g., $40k across 15 trades)
- **Quick Portfolio Summary** (`--quick` flag) - fast overview using positions endpoint
- **Test Harness** - automated tests against known anomaly accounts (`uv run python -m tests.test_anomaly_detection`)
- **Lowered thresholds** - `large_trade_usd`: $20k → $5k, `low_history_threshold`: 10 → 20 trades
- **Bug fixes** - timestamp parsing, memory limits for large trade histories

## License

MIT
