"""Configuration loader for Polymarket Watcher."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class DetectionConfig:
    # Low history detector
    large_trade_usd: float
    low_history_threshold: int
    cache_ttl_hours: int
    # Profitable trader detector
    min_trades_for_analysis: int = 50
    min_profit_factor: float = 2.0
    min_win_rate: float = 0.65
    high_frequency_threshold: int = 100


@dataclass
class LoggingConfig:
    level: str
    file: str
    max_file_size_mb: int
    backup_count: int


@dataclass
class ApiConfig:
    data_api_base: str
    gamma_api_base: str
    websocket_url: str
    requests_per_minute: int


@dataclass
class DatabaseConfig:
    path: str


@dataclass
class Config:
    detection: DetectionConfig
    logging: LoggingConfig
    api: ApiConfig
    database: DatabaseConfig


def load_config(config_path: str | Path = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return Config(
        detection=DetectionConfig(**raw["detection"]),
        logging=LoggingConfig(**raw["logging"]),
        api=ApiConfig(**raw["api"]),
        database=DatabaseConfig(**raw["database"]),
    )
