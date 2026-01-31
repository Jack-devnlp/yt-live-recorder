"""Structured logging for YouTube Live Recorder."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors
        self.format_str = '[%(asctime)s] %(levelname)s: %(message)s'

    def format(self, record: logging.LogRecord) -> str:
        # Create timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')

        # Format the message
        if self.use_colors and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            reset = self.RESET
            return f"{color}[{timestamp}]{reset} {record.levelname}: {record.getMessage()}"
        else:
            return f"[{timestamp}] {record.levelname}: {record.getMessage()}"


class ChannelLogFilter(logging.Filter):
    """Filter that adds channel context to log records."""

    def __init__(self, channel_name: Optional[str] = None):
        super().__init__()
        self.channel_name = channel_name

    def filter(self, record: logging.LogRecord) -> bool:
        if self.channel_name:
            record.msg = f"[{self.channel_name}] {record.msg}"
        return True


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    use_colors: bool = True
) -> logging.Logger:
    """Set up structured logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path to write logs to.
        use_colors: Whether to use colored output for console.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger('yt_recorder')
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = ColoredFormatter(use_colors=use_colors)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_channel_logger(channel_name: str, parent_logger: logging.Logger) -> logging.Logger:
    """Get a logger with channel context.

    Args:
        channel_name: Name of the channel.
        parent_logger: Parent logger to inherit from.

    Returns:
        Logger with channel context.
    """
    logger = logging.getLogger(f'yt_recorder.{channel_name}')
    logger.setLevel(parent_logger.level)

    # Add channel filter to all handlers
    channel_filter = ChannelLogFilter(channel_name)
    for handler in logger.handlers:
        handler.addFilter(channel_filter)

    return logger
