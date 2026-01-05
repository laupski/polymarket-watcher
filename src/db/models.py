"""SQLite database schema and models."""

SCHEMA = """
-- Cache wallet trade counts to avoid repeated API calls
CREATE TABLE IF NOT EXISTS wallet_cache (
    address TEXT PRIMARY KEY,
    trade_count INTEGER NOT NULL,
    first_trade_at TIMESTAMP,
    last_updated TIMESTAMP NOT NULL
);

-- Log all detected anomalies
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_type TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    trade_size_usd REAL NOT NULL,
    wallet_trade_count INTEGER,
    market_id TEXT,
    market_name TEXT,
    outcome TEXT,
    side TEXT,
    transaction_hash TEXT,
    details TEXT
);

-- Store trades for analysis (optional, can be disabled)
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_hash TEXT UNIQUE,
    wallet_address TEXT NOT NULL,
    market_id TEXT,
    market_slug TEXT,
    outcome TEXT,
    side TEXT,
    size REAL NOT NULL,
    price REAL NOT NULL,
    usd_value REAL NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_wallet_cache_last_updated ON wallet_cache(last_updated);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_wallet ON alerts(wallet_address);
CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(wallet_address);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
"""
