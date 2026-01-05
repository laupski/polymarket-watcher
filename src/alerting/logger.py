"""Alert logging - formats and outputs alerts to console and file."""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..db import Alert


class AlertFormatter(logging.Formatter):
    """Custom formatter for alert messages."""

    ALERT_FORMAT = """
================================================================================
{timestamp} | ALERT | {alert_type}
--------------------------------------------------------------------------------
  Wallet:      {wallet}
  Trade Size:  ${trade_size:,.2f}
  History:     {trade_count} previous trades
  Market:      {market}
  Outcome:     {outcome}
  Side:        {side}
  Tx:          {tx_hash}
================================================================================
"""

    def format(self, record: logging.LogRecord) -> str:
        if hasattr(record, "alert"):
            return self._format_alert(record.alert)
        return super().format(record)

    def _format_alert(self, alert: Alert) -> str:
        return self.ALERT_FORMAT.format(
            timestamp=alert.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            alert_type=alert.alert_type.upper().replace("_", " "),
            wallet=alert.wallet_address,
            trade_size=alert.trade_size_usd,
            trade_count=alert.wallet_trade_count or 0,
            market=alert.market_name or "Unknown",
            outcome=alert.outcome or "Unknown",
            side=alert.side or "Unknown",
            tx_hash=alert.transaction_hash or "Unknown",
        )


class AlertLogger:
    """Handles alert output to console and file."""

    def __init__(
        self,
        log_file: str | Path,
        log_level: str = "INFO",
        max_file_size_mb: int = 10,
        backup_count: int = 5,
    ):
        self.log_file = Path(log_file)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.backup_count = backup_count

        self._logger = logging.getLogger("polymarket_watcher.alerts")
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging handlers."""
        self._logger.setLevel(self.log_level)
        self._logger.handlers.clear()

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Console handler with colored output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(AlertFormatter())
        self._logger.addHandler(console_handler)

        # File handler with rotation
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(AlertFormatter())
        self._logger.addHandler(file_handler)

    def log_alert(self, alert: Alert):
        """Log an alert to console and file."""
        record = self._logger.makeRecord(
            name="polymarket_watcher.alerts",
            level=logging.WARNING,
            fn="",
            lno=0,
            msg="Alert triggered",
            args=(),
            exc_info=None,
        )
        record.alert = alert
        self._logger.handle(record)

    def info(self, message: str):
        """Log an info message."""
        self._logger.info(message)

    def warning(self, message: str):
        """Log a warning message."""
        self._logger.warning(message)

    def error(self, message: str):
        """Log an error message."""
        self._logger.error(message)


def setup_app_logging(level: str = "INFO"):
    """Set up application-wide logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from libraries
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
