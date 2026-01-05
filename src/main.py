"""Main entry point for Polymarket Watcher."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .alerting import AlertLogger, setup_app_logging
from .api import DataApiClient, RtdsWebSocketClient, Trade
from .config import Config, load_config
from .db import Repository
from .detection import (
    DetectionEngine,
    LowHistoryDetector,
    LowHistoryDetectorConfig,
    ProfitableTraderConfig,
    ProfitableTraderDetector,
)

logger = logging.getLogger(__name__)


class PolymarketWatcher:
    """Main application class that orchestrates all components."""

    def __init__(self, config: Config):
        self.config = config
        self._running = False

        # Initialize components
        self.repository = Repository(config.database.path)
        self.data_api = DataApiClient(config.api.data_api_base)
        self.alert_logger = AlertLogger(
            log_file=config.logging.file,
            log_level=config.logging.level,
            max_file_size_mb=config.logging.max_file_size_mb,
            backup_count=config.logging.backup_count,
        )

        # Detection engine
        self.engine = DetectionEngine(self.repository)

        # WebSocket client
        self.ws_client = RtdsWebSocketClient(
            on_trade=self._on_trade,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
        )

    async def start(self):
        """Start the watcher."""
        logger.info("Starting Polymarket Watcher...")

        # Initialize database
        await self.repository.initialize()

        # Set up detectors
        low_history_config = LowHistoryDetectorConfig(
            large_trade_usd=self.config.detection.large_trade_usd,
            low_history_threshold=self.config.detection.low_history_threshold,
            cache_ttl_hours=self.config.detection.cache_ttl_hours,
        )
        low_history_detector = LowHistoryDetector(
            config=low_history_config,
            repository=self.repository,
            data_api=self.data_api,
        )
        self.engine.add_detector(low_history_detector)

        # Set up profitable trader detector
        profitable_trader_config = ProfitableTraderConfig(
            min_trades_for_analysis=self.config.detection.min_trades_for_analysis,
            min_profit_factor=self.config.detection.min_profit_factor,
            min_win_rate=self.config.detection.min_win_rate,
            high_frequency_threshold=self.config.detection.high_frequency_threshold,
            cache_ttl_hours=self.config.detection.cache_ttl_hours,
        )
        profitable_trader_detector = ProfitableTraderDetector(
            config=profitable_trader_config,
            repository=self.repository,
            data_api=self.data_api,
        )
        self.engine.add_detector(profitable_trader_detector)

        logger.info(
            f"Detection thresholds: large_trade=${self.config.detection.large_trade_usd:,.0f}, "
            f"low_history_threshold={self.config.detection.low_history_threshold}, "
            f"min_win_rate={self.config.detection.min_win_rate * 100:.0f}%"
        )

        # Start WebSocket connection
        self._running = True
        await self.ws_client.connect()

    async def stop(self):
        """Stop the watcher gracefully."""
        logger.info("Stopping Polymarket Watcher...")
        self._running = False

        await self.ws_client.disconnect()
        await self.data_api.close()
        await self.repository.close()

        # Log final stats
        stats = self.engine.stats
        logger.info(
            f"Final stats: {stats['trades_processed']} trades processed, "
            f"{stats['alerts_generated']} alerts generated"
        )

    async def _on_connect(self):
        """Handle WebSocket connection."""
        logger.info("Connected to Polymarket real-time data stream")
        logger.info("Listening for trades...")

    async def _on_disconnect(self):
        """Handle WebSocket disconnection."""
        logger.warning("Disconnected from Polymarket real-time data stream")

    async def _on_trade(self, trade: Trade):
        """Process an incoming trade."""
        # Log trade at debug level
        logger.debug(
            f"Trade: {trade.side} {trade.size:.2f} @ ${trade.price:.4f} "
            f"(${trade.usd_value:,.2f}) - {trade.outcome}"
        )

        # Run detection
        alerts = await self.engine.process_trade(trade)

        # Log any alerts
        for alert in alerts:
            self.alert_logger.log_alert(alert)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Polymarket Watcher - Monitor for anomalous trading behavior"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def main_async(args):
    """Async main function."""
    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)

    # Override log level if debug flag is set
    if args.debug:
        config.logging.level = "DEBUG"

    # Set up logging
    setup_app_logging(config.logging.level)

    # Create and start watcher
    watcher = PolymarketWatcher(config)

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Start watcher in background
    watcher_task = asyncio.create_task(watcher.start())

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Stop watcher
    await watcher.stop()
    watcher_task.cancel()

    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


def main():
    """Main entry point."""
    args = parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
